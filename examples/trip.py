"""Tool use: the model calls your @tools and chains their results to answer.

`react` hands the model the tools and lets *it* decide which to call, in what
order, with what arguments — native function-calling, not text parsing. This
question can't be answered in one shot: the model has to look up a distance, then
feed it into two more tools (drive time, fuel cost). The tools are ordinary,
deterministic Python; the model just orchestrates them.

Run it:
  uv run jdsl run examples/trip.py -i request="Driving Nairobi to Mombasa — how long and how much fuel?"
"""

from jdsl import react, root, tool

_ROAD_KM = {
    ("mombasa", "nairobi"): 485,
    ("kisumu", "nairobi"): 340,
    ("nairobi", "nakuru"): 160,
}


@tool
def distance_km(origin: str, destination: str) -> int:
    """Road distance between two Kenyan cities, in kilometers."""
    return _ROAD_KM.get(tuple(sorted((origin.strip().lower(), destination.strip().lower()))), -1)


@tool
def drive_hours(km: int) -> float:
    """Driving time in hours to cover `km` (average highway speed)."""
    return round(km / 80, 1)


@tool
def fuel_cost(km: int) -> float:
    """Fuel cost in KES to cover `km` (8 L/100km at 180 KES/L)."""
    return round(km / 100 * 8 * 180, 2)


skill = (
    root("Trip", system="You are a driving assistant. Use tools for every number — never estimate.")
    .model("deepseek-chat")
    .do(react("request -> answer", tools=[distance_km, drive_hours, fuel_cost], max_steps=8))
)


if __name__ == "__main__":
    ctx = skill.run(request="I'm driving from Nairobi to Mombasa. How long will it take, and what's the fuel cost?")
    print("answer:", ctx.blackboard.get("answer"))
    # expected: 485 km -> ~6.1 h at 80 km/h, fuel = 485/100 * 8 * 180 = 6,984 KES
