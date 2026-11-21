"""
SUDOKU SOLVER — WEB BACKEND
===========================
A small Flask server that serves the front end and exposes the DMS/CSP
solver (sudoku_solver.py in the parent folder) over two JSON endpoints:

  POST /api/solve  {puzzle: [[9 x 9 ints]]}
      -> {ok, solution, nodes}          final answer only

  POST /api/steps  {puzzle: [[9 x 9 ints]]}
      -> {ok, steps: [...], nodes}      every search step, for animation

Each step = {type, desc, focus?, domains} where `domains` maps every cell
"rc" (e.g. "34" = row 3, col 4) to its candidate set as a digit string.
That snapshot is what lets the UI draw live D(cell) sets.

Run:  python app.py   ->  open http://127.0.0.1:5000
"""

import json
import sys
from copy import deepcopy
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# Import the solver from the parent directory by file path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sudoku_solver as solver          # noqa: E402  (NEIGHBORS, CSP helpers)

app = Flask(__name__, static_folder="static", static_url_path="")


# ----------------------------------------------------------------------------
# Step-recording solver: mirrors sudoku_solver.solve(), but appends a UI
# state to `steps` at every interesting moment (propagation, branching,
# value trial, backtrack, solution).
# ----------------------------------------------------------------------------

def snapshot(domains):
    """81 cells -> {"rc": "candidate digits", ...} e.g. "34": "2358"."""
    return {f"{r}{c}": "".join(map(str, sorted(d)))
            for (r, c), d in domains.items()}


def solve_with_steps(domains):
    """Same CSP algorithm as sudoku_solver.solve, but records every state."""
    steps = []

    def rec(domains):
        stats = {"forced": 0}
        domains = solver.propagate_singles(deepcopy(domains), stats)
        if domains is None:
            steps.append({"type": "contradiction",
                          "desc": "Contradiction during propagation — backtrack",
                          "domains": steps[-1]["domains"] if steps else {}})
            return None
        steps.append({"type": "propagate",
                      "desc": f"Propagation (closure) forced {stats['forced']} "
                              f"value(s)",
                      "domains": snapshot(domains)})
        if solver.is_solved(domains):
            steps.append({"type": "solution", "desc": "Solved!",
                          "domains": snapshot(domains)})
            return domains

        cell = solver.select_mrv(domains)
        if cell is None:
            return None
        r, c = cell
        dom = sorted(domains[cell])

        for value in dom:
            steps.append({"type": "branch", "focus": f"{r}{c}",
                          "desc": f"MRV: cell ({r},{c}) has the smallest "
                                  f"domain {dom} — try {value}",
                          "domains": snapshot(domains)})
            reduced = solver.forward_check(domains, cell, value)
            if reduced is None:
                steps.append({"type": "fail", "focus": f"{r}{c}",
                              "desc": f"{value} impossible at ({r},{c}) — "
                                      f"a neighbor's domain became empty",
                              "domains": snapshot(domains)})
                continue
            steps.append({"type": "assign", "focus": f"{r}{c}", "value": value,
                          "desc": f"Assign ({r},{c}) = {value}, then forward-"
                                  f"check (prune neighbors)",
                          "domains": snapshot(reduced)})
            result = rec(reduced)
            if result is not None:
                return result
            steps.append({"type": "backtrack", "focus": f"{r}{c}",
                          "desc": f"Subtree under ({r},{c})={value} exhausted "
                                  f"— backtrack",
                          "domains": snapshot(domains)})
        return None

    result = rec(deepcopy(domains))
    return steps, (result is not None)


# ----------------------------------------------------------------------------
# Input validation: a 9x9 list of lists, 0-9, no repeated clue in a group
# ----------------------------------------------------------------------------

def validate(puzzle):
    if (not isinstance(puzzle, list) or len(puzzle) != 9
            or any(len(row) != 9 for row in puzzle)):
        return "puzzle must be a 9x9 grid"
    for r in range(9):
        for c in range(9):
            if not isinstance(puzzle[r][c], int) or not 0 <= puzzle[r][c] <= 9:
                return f"cell ({r},{c}) must be an integer 0-9"
    for r in range(9):                                  # rows
        vals = [v for v in puzzle[r] if v]
        if len(vals) != len(set(vals)):
            return f"duplicate clue in row {r}"
    for c in range(9):                                  # columns
        vals = [puzzle[r][c] for r in range(9) if puzzle[r][c]]
        if len(vals) != len(set(vals)):
            return f"duplicate clue in column {c}"
    for br in (0, 3, 6):                                # boxes
        for bc in (0, 3, 6):
            vals = [puzzle[r][c] for r in range(br, br + 3)
                    for c in range(bc, bc + 3) if puzzle[r][c]]
            if len(vals) != len(set(vals)):
                return f"duplicate clue in box ({br},{bc})"
    return None


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/solve")
def api_solve():
    data = request.get_json(silent=True) or {}
    err = validate(data.get("puzzle"))
    if err:
        return jsonify(ok=False, error=err), 400
    domains = solver.parse_puzzle(
        "\n".join(" ".join(map(str, row)) for row in data["puzzle"]))
    result = solver.solve(deepcopy(domains))
    if result is None:
        return jsonify(ok=False, error="No solution — the puzzle is "
                                       "unsatisfiable"), 200
    solved, nodes = result
    grid = [[next(iter(solved[(r, c)])) for c in range(9)] for r in range(9)]
    return jsonify(ok=True, solution=grid, nodes=nodes)


@app.post("/api/steps")
def api_steps():
    data = request.get_json(silent=True) or {}
    err = validate(data.get("puzzle"))
    if err:
        return jsonify(ok=False, error=err), 400
    domains = solver.parse_puzzle(
        "\n".join(" ".join(map(str, row)) for row in data["puzzle"]))
    steps, ok = solve_with_steps(deepcopy(domains))
    return jsonify(ok=ok, steps=steps, nodes=len(steps))


if __name__ == "__main__":
    print("Sudoku CSP visualizer -> http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
