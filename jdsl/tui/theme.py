"""The workbench's single, self-contained color palette."""

from textual.theme import Theme

# Palette: sainnhe/gruvbox-material, as adapted by curbol/omarchy-gruvbox-material.
GRUVBOX_MATERIAL = Theme(
    name="gruvbox-material",
    primary="#e78a4e",
    secondary="#7daea3",
    accent="#d8a657",
    foreground="#d4be98",
    background="#282828",
    surface="#32302f",
    panel="#45403d",
    success="#a9b665",
    warning="#d8a657",
    error="#ea6962",
    dark=True,
    variables={
        "fg-bright": "#ddc7a1",
        "fg-soft": "#a89984",
        "muted": "#928374",
        "faint": "#7c6f64",
        "well": "#1b1b1b",
        "deep": "#141414",
        "selection": "#45403d",
        "residual": "#d3869b",
        "ref": "#89b482",
        "tint": "#744527",
    },
)

__all__ = ["GRUVBOX_MATERIAL"]
