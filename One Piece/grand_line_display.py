"""
GRAND LINE AGENT  -  FILE 2 OF 2 : DISPLAY
===========================================
Only drawing code lives here. These functions READ the state of the
objects (positions, score, fuel...) and draw it. They never change the
game. Game logic is in grand_line_logic.py (keep both in one folder).
"""

import pygame

from grand_line_logic import (
    GRID_WIDTH, GRID_HEIGHT, CELL, SIDEBAR_WIDTH, WINDOW_HEIGHT,
    MARINE_DETECT_RADIUS, RESTART_BUTTON, END_STATES,
)


# ----------------------------------------------------------------------------
# COLORS  (R, G, B)
# ----------------------------------------------------------------------------
BACKGROUND = (10, 40, 70)
GRID_LINE = (20, 60, 100)
SIDEBAR_BG = (18, 22, 30)
TEXT = (235, 235, 235)
TEXT_DIM = (150, 160, 170)
GREEN = (100, 220, 130)
RED = (220, 70, 70)
YELLOW = (255, 220, 120)
ORANGE = (255, 90, 60)
WHITE = (255, 255, 255)

PIRATE_COLOR = (255, 215, 0)
MARINE_COLOR = (220, 60, 60)
HQ_COLOR = (120, 30, 140)
VISITED_COLOR = (90, 90, 90)

# colour and letter shown on each type of island
ISLAND_COLORS = {
    "normal": (80, 190, 120),
    "treasure": (235, 190, 60),
    "legendary": (235, 120, 230),
    "supply": (80, 170, 235),
    "final": (90, 220, 200),
}
ISLAND_LETTERS = {"normal": "N", "treasure": "T", "legendary": "L", "supply": "S", "final": "F"}

# colour of the message box for each message kind
MESSAGE_COLORS = {"dim": TEXT_DIM, "info": YELLOW, "good": GREEN, "bad": RED, "fire": ORANGE}

# ----------------------------------------------------------------------------
# SIDEBAR LAYOUT
# ----------------------------------------------------------------------------
LINE_HEIGHT = 16
GAP = 5
BOTTOM_PART_Y = RESTART_BUTTON.bottom + 6    # "Reward Tiers" starts below the button
MESSAGE_BOX_Y = 522
MESSAGE_BOX_HEIGHT = 26


def grid_to_pixel(cell):
    """Converts a grid cell (col, row) to the pixel at the centre of that cell."""
    col, row = cell
    return col * CELL + CELL // 2, row * CELL + CELL // 2


# ----------------------------------------------------------------------------
# DRAWING THE OCEAN
# ----------------------------------------------------------------------------

def draw_grid(screen):
    for x in range(0, GRID_WIDTH * CELL, CELL):
        pygame.draw.line(screen, GRID_LINE, (x, 0), (x, GRID_HEIGHT * CELL))
    for y in range(0, GRID_HEIGHT * CELL, CELL):
        pygame.draw.line(screen, GRID_LINE, (0, y), (GRID_WIDTH * CELL, y))


def draw_transparent_circle(screen, color, center, radius, alpha):
    """Draws a see-through circle (used for the danger zones)."""
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*color, alpha), (radius, radius), radius)
    screen.blit(layer, (center[0] - radius, center[1] - radius))


def draw_hq_islands(screen, hq_islands):
    for hq in hq_islands:
        center = grid_to_pixel(hq.position)

        # three circles of increasing darkness show the danger zone
        draw_transparent_circle(screen, HQ_COLOR, center, 3 * CELL, 30)
        draw_transparent_circle(screen, HQ_COLOR, center, 2 * CELL, 55)
        draw_transparent_circle(screen, HQ_COLOR, center, 1 * CELL, 85)

        pygame.draw.circle(screen, HQ_COLOR, center, CELL // 2)
        pygame.draw.circle(screen, WHITE, center, CELL // 2, 2)


def draw_marines(screen, marine_ships):
    for ship in marine_ships:
        center = grid_to_pixel(ship.position)

        # firing range
        draw_transparent_circle(screen, MARINE_COLOR, center, MARINE_DETECT_RADIUS * CELL, 30)

        # the ship itself (a red square)
        box = pygame.Rect(0, 0, CELL - 8, CELL - 8)
        box.center = center
        pygame.draw.rect(screen, MARINE_COLOR, box, border_radius=4)
        pygame.draw.rect(screen, WHITE, box, 2, border_radius=4)

        # thin line showing its patrol route
        corner_pixels = [grid_to_pixel(c) for c in ship.corners]
        pygame.draw.lines(screen, (180, 60, 60), True, corner_pixels, 1)


def draw_islands(screen, islands, font):
    for island in islands:
        center = grid_to_pixel(island.position)

        if island.visited:
            color = VISITED_COLOR           # grey once collected
        else:
            color = ISLAND_COLORS[island.island_type]

        pygame.draw.circle(screen, color, center, CELL // 2 - 2)
        pygame.draw.circle(screen, WHITE, center, CELL // 2 - 2, 2)

        letter = font.render(ISLAND_LETTERS[island.island_type], True, (20, 20, 20))
        screen.blit(letter, letter.get_rect(center=center))


def draw_start(screen, start_position):
    pygame.draw.circle(screen, (150, 150, 150), grid_to_pixel(start_position), CELL // 2 - 4, 2)


def draw_planned_path(screen, agent):
    """Draws the dashed white line of the route the A* algorithm planned."""
    if len(agent.path) < 2:
        return
    if agent.state not in ("NAVIGATING", "WAITING", "REPLANNING"):
        return

    points = [grid_to_pixel(c) for c in agent.path[agent.path_index:]]
    for i in range(0, len(points) - 1, 2):      # every second segment -> dashed
        pygame.draw.line(screen, WHITE, points[i], points[i + 1], 2)


def draw_ship(screen, agent):
    """The pirate ship is a triangle. It turns orange when under fire."""
    cx, cy = grid_to_pixel(agent.position)
    triangle = [
        (cx, cy - CELL // 2 + 2),                       # top
        (cx - CELL // 2 + 4, cy + CELL // 2 - 4),       # bottom left
        (cx + CELL // 2 - 4, cy + CELL // 2 - 4),       # bottom right
    ]
    color = ORANGE if agent.under_fire else PIRATE_COLOR
    pygame.draw.polygon(screen, color, triangle)
    pygame.draw.polygon(screen, (0, 0, 0), triangle, 2)


# ----------------------------------------------------------------------------
# DRAWING THE SIDEBAR
# ----------------------------------------------------------------------------

def draw_restart_button(screen, font_bold, mouse_pos):
    hovered = RESTART_BUTTON.collidepoint(mouse_pos)
    color = (80, 105, 150) if hovered else (48, 58, 80)     # lighter when hovered

    pygame.draw.rect(screen, color, RESTART_BUTTON, border_radius=5)
    pygame.draw.rect(screen, WHITE, RESTART_BUTTON, 2, border_radius=5)
    label = font_bold.render("RESTART GAME", True, WHITE)
    screen.blit(label, label.get_rect(center=RESTART_BUTTON.center))


def draw_sidebar(screen, font, font_bold, agent, islands, mouse_pos):
    left = GRID_WIDTH * CELL            # x where the sidebar starts
    pygame.draw.rect(screen, SIDEBAR_BG, pygame.Rect(left, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))

    # small helper: write one line of text at height y, return the next y
    def write(text, text_font, color, y):
        if text:
            screen.blit(text_font.render(text, True, color), (left + 14, y))
        return y + LINE_HEIGHT

    # --- what to show in the state line ---
    if agent.state == "FINISHED":
        state_text, state_color, hint = "MISSION COMPLETE!", GREEN, "Press R or click RESTART"
    elif agent.state == "OUT_OF_FUEL":
        state_text, state_color, hint = "MISSION FAILED - OUT OF FUEL", RED, "Press R or click RESTART"
    elif agent.state == "CAPTURED":
        state_text, state_color, hint = "MISSION FAILED - CAPTURED", RED, "Press R or click RESTART"
    elif agent.state == "SUNK":
        state_text, state_color, hint = "MISSION FAILED - SHIP SUNK", RED, "Press R or click RESTART"
    elif agent.under_fire:
        state_text, state_color, hint = "State: " + agent.state + "  [UNDER FIRE]", ORANGE, ""
    else:
        state_text, state_color, hint = "State: " + agent.state, TEXT, ""

    # --- top part: live status ---
    y = 10
    y = write("GRAND LINE AGENT", font_bold, TEXT, y)
    y = write("Fully autonomous - the AI pilots itself", font, TEXT_DIM, y)
    y += GAP
    y = write(state_text, font_bold, state_color, y)
    y = write(hint, font, TEXT_DIM, y)
    y = write("Fuel: " + str(max(agent.fuel, 0)), font, TEXT, y)
    y = write("Score: " + str(agent.score), font, TEXT, y)
    y = write("Streak: x" + str(agent.streak), font, TEXT, y)

    y += GAP
    y = write("-- Decision --", font_bold, TEXT_DIM, y)
    if agent.target:
        name = agent.target.island_type.title()
        y = write("Target: " + name + " (U:" + str(int(agent.target_utility)) + ")", font, TEXT_DIM, y)
    else:
        y = write("Target: -", font, TEXT_DIM, y)

    y += GAP
    y = write("-- Statistics --", font_bold, TEXT_DIM, y)
    y = write("Distance travelled: " + str(agent.distance_travelled), font, TEXT_DIM, y)
    y = write("Islands collected: " + str(agent.islands_collected), font, TEXT_DIM, y)
    y = write("Score lost to fire: " + str(agent.score_lost_to_fire), font, TEXT_DIM, y)

    draw_restart_button(screen, font_bold, mouse_pos)

    # --- bottom part: legend and island list ---
    y = BOTTOM_PART_Y
    y = write("-- Reward Tiers --", font_bold, TEXT_DIM, y)
    y = write("Normal +20   Treasure +50", font, TEXT_DIM, y)
    y = write("Legendary +100   Supply +15/+fuel", font, TEXT_DIM, y)
    y = write("Streak bonus +15 per level", font, TEXT_DIM, y)
    y += GAP
    y = write("-- Islands --", font_bold, TEXT_DIM, y)
    for island in islands:
        status = "visited" if island.visited else "open"
        line = island.island_type.title().ljust(10) + " +" + str(island.reward).ljust(4) + " [" + status + "]"
        y = write(line, font, TEXT_DIM, y)

    # --- message box at the very bottom ---
    if agent.message_timer > 0:
        color = MESSAGE_COLORS[agent.message_kind]
        box = pygame.Rect(left + 8, MESSAGE_BOX_Y, SIDEBAR_WIDTH - 16, MESSAGE_BOX_HEIGHT)
        pygame.draw.rect(screen, (30, 34, 44), box, border_radius=5)
        pygame.draw.rect(screen, color, box, 2, border_radius=5)

        text = agent.message
        while font.size(text)[0] > SIDEBAR_WIDTH - 28 and len(text) > 3:
            text = text[:-4] + "..."        # shorten if too long for the box
        rendered = font.render(text, True, color)
        screen.blit(rendered, rendered.get_rect(midleft=(left + 16, box.centery)))
