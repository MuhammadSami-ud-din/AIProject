"""Reads keyboard input and converts it to an Action for the human player.

Human controls:
  A / D  = move left / right (mapped to FORWARD / BACK based on facing)
  W      = jump
  J      = light attack
  K      = heavy attack
  L      = block
"""

import pygame

from backend.ai.actions import Action


def get_human_action(enemy_x, my_x):
    """Read the keyboard and return an Action.

    enemy_x and my_x are used to figure out which direction is 'forward'.
    """
    keys = pygame.key.get_pressed()

    # Attacks take priority
    if keys[pygame.K_j]:
        return Action.LIGHT
    if keys[pygame.K_k]:
        return Action.HEAVY

    # Block
    if keys[pygame.K_l]:
        return Action.BLOCK

    # Jump
    if keys[pygame.K_w]:
        return Action.JUMP

    # Movement: A = left, D = right
    # Convert to FORWARD / BACK based on where the enemy is
    facing_right = enemy_x >= my_x

    if keys[pygame.K_d]:
        return Action.FORWARD if facing_right else Action.BACK
    if keys[pygame.K_a]:
        return Action.BACK if facing_right else Action.FORWARD

    return Action.IDLE
