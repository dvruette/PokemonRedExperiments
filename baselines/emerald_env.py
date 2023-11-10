import os
from pathlib import Path
import shutil

import gymnasium as gym
import numpy as np
from pygba import PyGBAEnv, PyGBA
from pygba.utils import KEY_MAP

from emerald_wrapper import CustomEmeraldWrapper


class EmeraldEnv(PyGBAEnv):
    def __init__(
        self,
        gba: PyGBA,
        frames_path: str | Path | None = None,
        frame_save_freq: int = 1,
        early_stopping: bool = False,
        patience: int = 1024,
        rank: int = 0,
        **kwargs,
    ):
        game_wrapper = CustomEmeraldWrapper()
        super().__init__(gba, game_wrapper, **kwargs)
        self.frames_path = frames_path
        self.frame_save_freq = frame_save_freq
        self.early_stopping = early_stopping
        self.patience = patience
        self.rank = rank

        self.arrow_keys = [None, "up", "down", "right", "left"]
        # self.buttons = [None, "A", "B", "select", "start", "L", "R"]
        self.buttons = [None, "A", "B"]

        # cartesian product of arrows and buttons, i.e. can press 1 arrow and 1 button at the same time
        self.actions = [(a, b) for a in self.arrow_keys for b in self.buttons]
        self.action_space = gym.spaces.Discrete(len(self.actions))
        
        self._total_reward = 0
        self._max_reward = 0
        self._max_reward_step = 0
        self.agent_stats = []

    def step(self, action_id):
        info = {}

        actions = self.get_action_by_id(action_id)
        actions = [KEY_MAP[a] for a in actions if a is not None]

        if self.frames_path is not None and self.frame_save_freq > 0 and (self._step + 1) % self.frame_save_freq == 0:
            out_path = Path(self.frames_path) / f"{self.rank:02d}" / f"{self._step:06d}.jpg"
            if self._step == 0 or self._step + 1 == self.frame_save_freq:
                # delete old frames
                if out_path.parent.exists():
                    shutil.rmtree(out_path.parent)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            img = self._framebuffer.to_pil().convert("RGB")
            img.save(out_path)
            thumbnail_path = Path(self.frames_path) / f"{self.rank:02d}.jpg"
            thumbnail_path.write_bytes(out_path.read_bytes())

        if np.random.random() > self.repeat_action_probability:
            self.gba.core.set_keys(*actions)

        if isinstance(self.frameskip, tuple):
            frameskip = np.random.randint(*self.frameskip)
        else:
            frameskip = self.frameskip

        for _ in range(frameskip + 1):
            self.gba.core.run_frame()
            pass
        observation = self._get_observation()

        reward = 0
        done = False
        truncated = self.check_if_done()
        if self.game_wrapper is not None:
            reward = self.game_wrapper.reward(self.gba, observation)
            done = done or self.game_wrapper.game_over(self.gba, observation)
            info.update(self.game_wrapper.info(self.gba, observation))

        # the tensorboard will read out the agent_stats list and plot it
        self.agent_stats.append(info["rewards"])

        self._total_reward += reward
        if self._total_reward > self._max_reward:
            self._max_reward = reward
            self._max_reward_step = self._step
        self._step += 1
        reward_display = " | ".join(f"{k}={v:.3g}" for k, v in info["rewards"].items())
        print(f"\r step={self._step} | {reward_display}", end="", flush=True)

        return observation, reward, done, truncated, info
    
    def check_if_done(self):
        if self.max_episode_steps is not None and self._step >= self.max_episode_steps:
            return True
        if self.early_stopping and self._step - self._max_reward_step > self.patience:
            return True
        return False

    def reset(self, seed=None):
        return super().reset(seed=seed)
        self._total_reward = 0
        self._max_reward = 0
        self._max_reward_step = 0
        self.agent_stats = []
