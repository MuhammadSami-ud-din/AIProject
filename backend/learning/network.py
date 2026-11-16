"""PyTorch neural network architecture for Actor-Critic policy and value estimation.

Specifications:
  - 2 hidden layers of 128 units (fully connected) with Tanh / ReLU activations.
  - Action masking support: illegal moves receive -inf logits so they have 0% probability.
  - Dual heads: Actor (discrete distribution over 27 macro-actions) and Critic (scalar state value).
  - Designed for CPU execution with decision latency well under 1 ms.
"""

from typing import Optional, Tuple
import numpy as np
import torch
import torch.nn as nn
from torch.distributions.categorical import Categorical

from backend.learning.config import ACTION_DIM, HIDDEN_DIM, OBS_DIM


def layer_init(layer: nn.Linear, std: float = np.sqrt(2), bias_const: float = 0.0) -> nn.Linear:
    """Orthogonal layer initialization with custom gain and bias constant."""
    import numpy as np
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias_const)
    return layer


class ActorCritic(nn.Module):
    """Actor-Critic network for PPO and Behaviour Cloning warm start."""

    def __init__(self, obs_dim: int = OBS_DIM, action_dim: int = ACTION_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        import numpy as np

        # Shared feature extractor: 2 hidden layers of 128 units
        self.shared_net = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden_dim), np.sqrt(2)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, hidden_dim), np.sqrt(2)),
            nn.Tanh(),
        )

        # Actor head (policy logits)
        self.actor = layer_init(nn.Linear(hidden_dim, action_dim), 0.01)

        # Critic head (state value)
        self.critic = layer_init(nn.Linear(hidden_dim, 1), 1.0)

    def get_features(self, obs: torch.Tensor) -> torch.Tensor:
        """Pass observation through the shared hidden layers."""
        return self.shared_net(obs)

    def forward(
        self, obs: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute masked action logits and state value estimate."""
        hidden = self.shared_net(obs)
        logits = self.actor(hidden)

        if mask is not None:
            # Mask out illegal actions with a large negative number (-1e9)
            if mask.dtype != torch.bool:
                mask = mask.bool()
            logits = logits.masked_fill(~mask, -1e9)

        value = self.critic(hidden)
        return logits, value

    def get_action_and_value(
        self,
        obs: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        action: Optional[torch.Tensor] = None,
        temperature: float = 1.0,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Sample an action (or evaluate existing action) and compute log_prob and entropy."""
        logits, value = self.forward(obs, mask=mask)

        # Temperature scaling for exploration/personality variety
        if temperature > 0 and temperature != 1.0:
            logits = logits / temperature

        dist = Categorical(logits=logits)

        if action is None:
            action = dist.sample()

        log_prob = dist.log_prob(action)
        entropy = dist.entropy()

        return action, log_prob, entropy, value.squeeze(-1)

    def get_value(self, obs: torch.Tensor) -> torch.Tensor:
        """Compute only the state value."""
        hidden = self.shared_net(obs)
        return self.critic(hidden).squeeze(-1)
