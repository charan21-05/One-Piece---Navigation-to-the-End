"""
GRAND LINE AGENT  -  FILE 1 OF 2 : LOGIC, SEARCH ALGORITHM AND MAIN LOOP
=========================================================================
Project idea:
    A pirate ship is an AI agent. Nobody steers it. It has to reach the
    Final Island on its own, collecting rewards on the way, while
    avoiding Marine ships (they shoot) and World Government HQ (instant
    game over). Fuel is limited.

AI techniques used (classical AI only, NO machine learning):
    1. Utility-based decision making  -> which island should I go to?
    2. A* search algorithm            -> which path should I take?
    3. Finite state machine           -> what am I doing right now?

Agent cycle:
    PERCEIVE -> REASON -> DECIDE -> PLAN ROUTE -> ACT -> REPLAN IF NEEDED

Contents of this file:
    1. Settings
    2. World objects  (Island, Headquarters, MarineShip)
    3. Risk functions
    4. Utility function  (decision making)
    5. A* search         (path planning)
    6. The Agent         (state machine)
    7. Building the world + saving results
    8. Main game loop

All drawing code is in grand_line_display.py (keep both in one folder).

How to run:
    pip install pygame
    python grand_line_logic.py
Keys: R = restart, ESC = quit
"""

import csv
import heapq
import os
import sys

import pygame


# ============================================================================
# 1. SETTINGS
# ============================================================================

GRID_WIDTH = 36          # number of columns in the ocean
GRID_HEIGHT = 22         # number of rows in the ocean
CELL = 26                # size of one grid cell in pixels
SIDEBAR_WIDTH = 340      # width of the information panel on the right

WINDOW_WIDTH = GRID_WIDTH * CELL + SIDEBAR_WIDTH
WINDOW_HEIGHT = GRID_HEIGHT * CELL

# The restart button lives in the sidebar. It is defined here because the
# main loop needs it to detect mouse clicks.
RESTART_BUTTON = pygame.Rect(GRID_WIDTH * CELL + 8, 238, SIDEBAR_WIDTH - 16, 28)

FPS = 30
SHIP_MOVE_INTERVAL = 6      # the ship moves one cell every 6 frames
WAIT_DURATION = 25          # frames the ship waits when a marine blocks the way
MESSAGE_DURATION = 90       # frames a message stays visible

START_FUEL = 130
MARINE_DETECT_RADIUS = 2    # marines shoot if we are within this distance
BOMBARD_INTERVAL = 10       # frames between two shots
STREAK_BONUS = 15           # extra score per level of the collection streak
MAX_REPLAN_ATTEMPTS = 3     # after 3 reroutes the ship stops dodging and pushes on

# Agent states. The last four are "game over" states.
END_STATES = ("FINISHED", "OUT_OF_FUEL", "CAPTURED", "SUNK")


# ============================================================================
# 2. WORLD OBJECTS
# ============================================================================

class Island:
    """A reward island. It never moves."""

    # reward given for each type of island
    REWARDS = {"normal": 20, "treasure": 50, "legendary": 100, "supply": 15, "final": 30}

    def __init__(self, position, island_type, fuel_bonus=0):
        self.position = position            # (column, row)
        self.island_type = island_type
        self.reward = self.REWARDS[island_type]
        self.fuel_bonus = fuel_bonus        # only supply islands give fuel
        self.visited = False


class Headquarters:
    """World Government HQ. Touching it means instant failure."""

    def __init__(self, position):
        self.position = position


def build_patrol_path(corners):
    """
    A marine patrol is given as 4 corner points. This function fills in
    every single cell between the corners so the ship can move one cell
    at a time instead of jumping.
    Example: corners (0,0) -> (0,3) gives (0,0),(0,1),(0,2),(0,3)
    """
    path = [corners[0]]
    for i in range(len(corners)):
        start = corners[i]
        end = corners[(i + 1) % len(corners)]    # last corner connects to the first

        # direction of travel: -1, 0 or +1 on each axis
        step_x = (end[0] > start[0]) - (end[0] < start[0])
        step_y = (end[1] > start[1]) - (end[1] < start[1])

        cell = start
        while cell != end:
            cell = (cell[0] + step_x, cell[1] + step_y)
            path.append(cell)

    path.pop()      # the last cell is the same as the first, remove the duplicate
    return path


class MarineShip:
    """An enemy ship that patrols a rectangular loop forever."""

    def __init__(self, corners, step_interval):
        self.corners = corners
        self.path = build_patrol_path(corners)
        self.index = 0
        self.position = self.path[0]
        self.prev_position = self.path[0]
        self.step_interval = step_interval      # frames per step (bigger = slower)
        self.counter = 0

    def update(self):
        """Called every frame. Moves one cell when the counter is full."""
        self.counter += 1
        if self.counter >= self.step_interval:
            self.counter = 0
            self.prev_position = self.position
            self.index = (self.index + 1) % len(self.path)
            self.position = self.path[self.index]


# ============================================================================
# 3. RISK FUNCTIONS
# These are used by BOTH the decision maker and the A* search, so the
# agent's thinking and its path planning always agree on what is dangerous.
# ============================================================================

def manhattan(a, b):
    """Grid distance (no diagonal moves): |x1-x2| + |y1-y2|."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def risk_from_distance(d):
    """Converts a distance from a marine into a danger number."""
    if d == 0:
        return 60
    if d == 1:
        return 35
    if d == 2:
        return 15
    if d == 3:
        return 5
    return 0


def marine_risk(cell, marine_ships):
    """Danger at a cell from where the marines are RIGHT NOW."""
    total = 0
    for ship in marine_ships:
        total += risk_from_distance(manhattan(cell, ship.position))
    return total


def patrol_risk(cell, marine_ships):
    """
    Danger at a cell from the marines' whole PATROL ROUTES (not where they
    are standing right now). Without this, an island inside a patrol loop
    could look safe just because the marine is on the other side at that
    moment.
    """
    closest = 999
    for ship in marine_ships:
        for p in ship.path:
            closest = min(closest, manhattan(cell, p))
    return risk_from_distance(closest)


def hq_risk(cell, hq_islands):
    """Danger near a World Government HQ. Very high, because HQ = game over."""
    total = 0
    for hq in hq_islands:
        d = manhattan(cell, hq.position)
        if d == 0:
            total += 500
        elif d == 1:
            total += 120
        elif d == 2:
            total += 60
        elif d == 3:
            total += 20
    return total


def bombard_damage(distance):
    """Score lost per shot. Closer marine = more damage."""
    if distance == 0:
        return 8
    if distance == 1:
        return 6
    if distance == 2:
        return 4
    if distance == 3:
        return 2
    return 0


# ============================================================================
# 4. DECISION MAKING  (utility function)
# ============================================================================

def calculate_utility(position, fuel, island, hq_islands, marine_ships):
    """
    Gives every island a score. The agent goes to the island with the
    HIGHEST utility.

        utility = reward + fuel bonus - distance cost - danger cost

    - reward        : what we get for collecting it
    - fuel bonus    : supply islands refill fuel, so they are worth more
    - distance cost : far islands waste fuel and time (1.2 per cell)
    - danger cost   : HQ risk (x0.3) + marine patrol risk (x0.5)
    - if the island is farther than our fuel, we subtract 1000 so it is
      never chosen.
    """
    distance = manhattan(position, island.position)

    distance_cost = distance * 1.2
    danger_cost = hq_risk(island.position, hq_islands) * 0.3
    danger_cost += patrol_risk(island.position, marine_ships) * 0.5

    utility = island.reward + island.fuel_bonus - distance_cost - danger_cost

    if distance > fuel:
        utility -= 1000
    return utility


# ============================================================================
# 5. SEARCH ALGORITHM  (A* with risk)
# ============================================================================

def a_star(start, goal, marine_ships, hq_islands):
    """
    A* finds the cheapest path from start to goal on the grid.

        f(n) = g(n) + h(n)
        g(n) = real cost from start to n
        h(n) = Manhattan distance from n to goal   (the heuristic)

    Normal A* uses cost 1 per step. Ours is "risk-aware":

        cost of one step = 1 + marine risk + HQ risk of the new cell

    So the cheapest path is not always the shortest one, it is the one
    that stays away from danger. HQ cells are completely blocked.

    Returns a list of cells from start to goal, or None if no path exists.
    """
    if start == goal:
        return [start]

    blocked = [hq.position for hq in hq_islands]

    open_list = [(0, start)]        # priority queue of (f value, cell)
    came_from = {}                  # to rebuild the path at the end
    g_cost = {start: 0}
    done = set()                    # cells already fully explored

    while open_list:
        _, current = heapq.heappop(open_list)    # cell with the smallest f

        if current in done:
            continue
        done.add(current)

        # reached the goal -> walk backwards through came_from to get the path
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        # look at the 4 neighbours: right, left, down, up
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (current[0] + dx, current[1] + dy)

            # skip cells outside the grid
            if not (0 <= neighbour[0] < GRID_WIDTH and 0 <= neighbour[1] < GRID_HEIGHT):
                continue
            # skip HQ cells
            if neighbour in blocked:
                continue

            step_cost = 1 + marine_risk(neighbour, marine_ships) + hq_risk(neighbour, hq_islands)
            new_g = g_cost[current] + step_cost

            # keep this route only if it is cheaper than any found before
            if neighbour not in g_cost or new_g < g_cost[neighbour]:
                g_cost[neighbour] = new_g
                f = new_g + manhattan(neighbour, goal)
                heapq.heappush(open_list, (f, neighbour))
                came_from[neighbour] = current

    return None     # open list became empty -> no path


# ============================================================================
# 6. THE AGENT  (finite state machine)
# ============================================================================
# States:
#   DECIDING    choose the next island (utility)
#   PLANNING    find a path to it (A*)
#   NAVIGATING  sail along the path
#   WAITING     a marine is close, wait for it to move away
#   REPLANNING  a marine is close, find a new path
#   FINISHED / OUT_OF_FUEL / CAPTURED / SUNK   -> game over

class PirateShipAgent:

    def __init__(self, start_position, fuel=START_FUEL):
        self.position = start_position
        self.fuel = fuel
        self.score = 0
        self.streak = 0                 # islands collected in a row without being shot

        self.state = "DECIDING"
        self.target = None              # island we are heading to
        self.target_utility = 0         # its utility (shown in the sidebar)
        self.path = []
        self.path_index = 0
        self.replan_attempts = 0

        self.move_timer = 0
        self.wait_timer = 0
        self.bombard_timer = 0
        self.under_fire = False

        # message shown in the sidebar. kind is "info", "good", "bad" or "fire"
        self.message = "Perceiving the ocean and weighing its options..."
        self.message_kind = "dim"
        self.message_timer = MESSAGE_DURATION * 3

        # numbers used for performance measurement
        self.distance_travelled = 0
        self.islands_collected = 0
        self.score_lost_to_fire = 0
        self.replans = 0
        self.marine_encounters = 0

    def set_message(self, text, kind):
        self.message = text
        self.message_kind = kind
        self.message_timer = MESSAGE_DURATION

    # ---- PERCEIVE ----------------------------------------------------------
    def perceive(self, islands, marine_ships, hq_islands):
        """Collects what the agent knows about the world (first step of the cycle)."""
        return {
            "position": self.position,
            "fuel": self.fuel,
            "unvisited_islands": [i for i in islands if not i.visited],
            "marine_positions": [m.position for m in marine_ships],
            "hq_positions": [h.position for h in hq_islands],
        }

    # ---- REASON + DECIDE ---------------------------------------------------
    def choose_target(self, islands, marine_ships, hq_islands):
        """Scores all unvisited islands and returns the best one."""
        world = self.perceive(islands, marine_ships, hq_islands)

        best_island = None
        best_utility = None
        for island in world["unvisited_islands"]:
            u = calculate_utility(self.position, self.fuel, island, hq_islands, marine_ships)
            if best_utility is None or u > best_utility:
                best_utility = u
                best_island = island

        self.target_utility = best_utility
        return best_island

    # ---- helper functions for dodging marines ------------------------------
    def route_is_dangerous(self, marine_ships, lookahead=4):
        """Checks the next 4 cells of the path for a nearby marine."""
        next_cells = self.path[self.path_index: self.path_index + lookahead]
        for cell in next_cells:
            if marine_risk(cell, marine_ships) >= 35:
                return True
        return False

    def marine_moving_away(self, marine_ships):
        """True if the closest marine is getting farther from us."""
        closest = min(marine_ships, key=lambda m: manhattan(self.position, m.position))
        old_distance = manhattan(self.position, closest.prev_position)
        new_distance = manhattan(self.position, closest.position)
        return new_distance > old_distance

    def give_up_on_target(self, reason):
        """The target cannot be reached (no path or not enough fuel)."""
        if self.target.island_type == "final":
            # the final island cannot be skipped, so the mission fails
            self.state = "OUT_OF_FUEL"
            self.set_message("No safe route to the Final Island! " + reason, "bad")
            return
        self.target.visited = True      # mark as done so we do not choose it again
        self.set_message("Giving up on " + self.target.island_type.title() + " - " + reason, "bad")
        self.target = None
        self.state = "DECIDING"

    # ---- one step of the state machine (called every frame) ----------------
    def update(self, islands, marine_ships, hq_islands):
        if self.state in END_STATES:
            return

        if self.state == "DECIDING":
            self.do_deciding(islands, marine_ships, hq_islands)
        elif self.state == "PLANNING":
            self.do_planning(marine_ships, hq_islands)
        elif self.state == "NAVIGATING":
            self.do_navigating(marine_ships, hq_islands)
        elif self.state == "WAITING":
            self.do_waiting()
        elif self.state == "REPLANNING":
            self.do_replanning(marine_ships, hq_islands)

    def do_deciding(self, islands, marine_ships, hq_islands):
        target = self.choose_target(islands, marine_ships, hq_islands)
        if target is None:                  # nothing left to collect
            self.state = "FINISHED"
            return
        self.target = target
        self.replan_attempts = 0
        self.set_message("Decided: " + target.island_type.title() + " Island looks worth the trip.", "info")
        self.state = "PLANNING"

    def do_planning(self, marine_ships, hq_islands):
        path = a_star(self.position, self.target.position, marine_ships, hq_islands)

        if path is None:
            self.give_up_on_target("no safe route exists.")
            return
        if len(path) - 1 > self.fuel:       # path has (cells - 1) steps, 1 fuel per step
            self.give_up_on_target("not enough fuel for the trip.")
            return

        self.path = path
        self.path_index = 0
        self.state = "NAVIGATING"

    def do_navigating(self, marine_ships, hq_islands):
        # 1) Is a marine near our path? Then wait or reroute (limited attempts).
        if self.replan_attempts < MAX_REPLAN_ATTEMPTS and self.route_is_dangerous(marine_ships):
            self.marine_encounters += 1
            self.replan_attempts += 1
            if self.marine_moving_away(marine_ships):
                self.state = "WAITING"
                self.wait_timer = 0
                self.set_message("Marine ship nearby - waiting for it to clear the path.", "bad")
            else:
                self.state = "REPLANNING"
            return

        # 2) Otherwise move one cell every SHIP_MOVE_INTERVAL frames.
        self.move_timer += 1
        if self.move_timer < SHIP_MOVE_INTERVAL:
            return
        self.move_timer = 0

        if self.path_index < len(self.path) - 1:
            self.path_index += 1
            self.position = self.path[self.path_index]
            self.fuel -= 1
            self.distance_travelled += 1

            # safety check (A* already blocks HQ cells, so this should never happen)
            for hq in hq_islands:
                if hq.position == self.position:
                    self.state = "CAPTURED"
                    self.set_message("CAPTURED! Sailed into a World Government HQ.", "bad")
                    return

            if self.fuel <= 0:
                self.state = "OUT_OF_FUEL"
                self.set_message("Out of fuel! Mission failed.", "bad")
        else:
            self.arrive_at_island()     # end of the path reached

    def do_waiting(self):
        self.wait_timer += 1
        if self.wait_timer > WAIT_DURATION:
            self.state = "NAVIGATING"

    def do_replanning(self, marine_ships, hq_islands):
        self.replans += 1
        path = a_star(self.position, self.target.position, marine_ships, hq_islands)

        if path is None or len(path) - 1 > self.fuel:
            self.give_up_on_target("had to abandon the reroute.")
            return

        self.path = path
        self.path_index = 0
        self.state = "NAVIGATING"
        self.set_message("Rerouting around danger...", "info")

    def arrive_at_island(self):
        island = self.target
        island.visited = True
        self.islands_collected += 1

        streak_bonus = self.streak * STREAK_BONUS
        self.score += island.reward + streak_bonus
        self.fuel += island.fuel_bonus
        self.streak += 1

        text = "+" + str(island.reward) + " " + island.island_type.title() + "!"
        if streak_bonus:
            text += " +" + str(streak_bonus) + " streak bonus"
        if island.fuel_bonus:
            text += " (+" + str(island.fuel_bonus) + " fuel)"
        self.set_message(text, "info")

        if island.island_type == "final":
            fuel_bonus = max(self.fuel, 0)          # leftover fuel is added to the score
            self.score += fuel_bonus
            self.set_message("FINAL ISLAND REACHED! +" + str(fuel_bonus) + " fuel-efficiency bonus.", "good")
            self.state = "FINISHED"
            return

        self.target = None
        self.state = "DECIDING"

    # ---- marine bombardment (runs every frame, separate from movement) -----
    def update_bombardment(self, marine_ships):
        if self.state in END_STATES:
            self.under_fire = False
            return

        nearest = min((manhattan(self.position, m.position) for m in marine_ships), default=999)
        self.under_fire = nearest <= MARINE_DETECT_RADIUS

        if not self.under_fire:
            self.bombard_timer = 0
            return

        self.bombard_timer += 1
        if self.bombard_timer >= BOMBARD_INTERVAL:
            self.bombard_timer = 0
            damage = bombard_damage(nearest)
            score_before = self.score

            self.score = max(0, self.score - damage)
            self.score_lost_to_fire += damage
            self.streak = 0                         # being shot breaks the streak
            self.set_message("Under fire! -" + str(damage) + " score.", "fire")

            # We only sink if we HAD some score and it dropped to zero.
            # Being shot at score 0 (before collecting anything) is survivable.
            if score_before > 0 and self.score <= 0:
                self.state = "SUNK"
                self.set_message("SUNK! Marine bombardment wore your crew down to nothing.", "bad")


# ============================================================================
# 7. BUILDING THE WORLD + SAVING RESULTS
# ============================================================================

def build_world():
    """Creates a fresh ocean. Used at start and every time we restart."""
    start_position = (2, 11)

    islands = [
        Island((6, 3), "normal"),
        Island((6, 19), "normal"),
        Island((14, 5), "normal"),
        Island((20, 17), "normal"),
        Island((11, 10), "treasure"),
        Island((25, 4), "treasure"),
        Island((31, 15), "legendary"),
        Island((16, 14), "supply", fuel_bonus=45),
        Island((28, 9), "supply", fuel_bonus=45),
        Island((34, 10), "final"),
    ]

    hq_islands = [
        Headquarters((19, 9)),
        Headquarters((29, 17)),
    ]

    marine_ships = [
        MarineShip([(9, 6), (9, 14), (16, 14), (16, 6)], step_interval=7),
        MarineShip([(21, 3), (21, 11), (27, 11), (27, 3)], step_interval=8),
        MarineShip([(23, 13), (23, 19), (32, 19), (32, 13)], step_interval=9),
        MarineShip([(4, 4), (4, 9), (10, 9), (10, 4)], step_interval=8),
    ]

    agent = PirateShipAgent(start_position, fuel=START_FUEL)
    return islands, hq_islands, marine_ships, agent, start_position


def save_result(agent, filename="run_history.csv"):
    """
    Performance measurement: after every run, one row is added to a CSV
    file. Running the game many times gives a table we can compare
    (for example, with different START_FUEL values).
    """
    row = {
        "outcome": agent.state,
        "score": agent.score,
        "fuel_remaining": max(agent.fuel, 0),
        "distance_travelled": agent.distance_travelled,
        "islands_collected": agent.islands_collected,
        "replans": agent.replans,
        "marine_encounters": agent.marine_encounters,
        "score_lost_to_fire": agent.score_lost_to_fire,
    }

    file_is_new = not os.path.exists(filename)
    with open(filename, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if file_is_new:
            writer.writeheader()        # column names only once
        writer.writerow(row)


# ============================================================================
# 8. MAIN GAME LOOP
# ============================================================================

def main():
    # The display file imports settings from THIS file, so we import it here
    # (inside the function) to avoid a circular import.
    from grand_line_display import (
        draw_grid, draw_hq_islands, draw_start, draw_islands,
        draw_marines, draw_planned_path, draw_ship, draw_sidebar, BACKGROUND,
    )

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Grand Line Agent - Autonomous")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 13)
    font_bold = pygame.font.SysFont("consolas", 14, bold=True)
    island_font = pygame.font.SysFont("consolas", 15, bold=True)

    islands, hq_islands, marine_ships, agent, start_position = build_world()
    result_saved = False

    running = True
    while running:

        # ---- 1. handle input ----
        for event in pygame.event.get():
            restart = False
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    restart = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if RESTART_BUTTON.collidepoint(event.pos):
                    restart = True

            if restart:
                islands, hq_islands, marine_ships, agent, start_position = build_world()
                result_saved = False

        # ---- 2. update the world ----
        for ship in marine_ships:
            ship.update()
        agent.update(islands, marine_ships, hq_islands)
        agent.update_bombardment(marine_ships)

        # save the result once, when the run ends
        if agent.state in END_STATES and not result_saved:
            save_result(agent)
            result_saved = True

        # ---- 3. draw everything ----
        screen.fill(BACKGROUND)
        draw_grid(screen)
        draw_hq_islands(screen, hq_islands)
        draw_start(screen, start_position)
        draw_islands(screen, islands, island_font)
        draw_marines(screen, marine_ships)
        draw_planned_path(screen, agent)
        draw_ship(screen, agent)
        draw_sidebar(screen, font, font_bold, agent, islands, pygame.mouse.get_pos())

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # Import under the real module name so the display file uses this same
    # module instead of loading a second copy of it.
    import grand_line_logic
    grand_line_logic.main()
