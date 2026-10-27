from __future__ import annotations

from dataclasses import dataclass

from digital_child.domain.models import EmotionName, EmotionState


@dataclass(frozen=True)
class FaceFrame:
    lines: list[str]
    expression: EmotionName
    blink: bool
    gaze: int


class TerminalFaceRenderer:
    """Original geometric terminal face with continuous idle micro-animation."""

    def __init__(self, ascii_only: bool = False) -> None:
        self.ascii_only = ascii_only

    def render(
        self,
        emotion: EmotionState,
        tick: int,
        *,
        override: EmotionName | None = None,
    ) -> FaceFrame:
        expression = override or emotion.dominant
        blink = tick % 73 in {0, 1, 2}
        gaze_cycle = (tick // 17) % 5
        if gaze_cycle == 0:
            gaze = -1
        elif gaze_cycle == 4:
            gaze = 1
        else:
            gaze = 0
        float_offset = 1 if (tick // 31) % 2 else 0

        features = self._features(expression, blink, gaze, tick)
        lines = (
            self._ascii_face(features, float_offset)
            if self.ascii_only
            else self._unicode_face(features, float_offset)
        )
        return FaceFrame(lines=lines, expression=expression, blink=blink, gaze=gaze)

    @staticmethod
    def _features(
        expression: EmotionName,
        blink: bool,
        gaze: int,
        tick: int,
    ) -> dict[str, str]:
        brows = {
            EmotionName.CURIOUS: ("╱━━", "━━╲"),
            EmotionName.SKEPTICAL: ("━━╲", "╱━━"),
            EmotionName.CONFUSED: ("╲━━", "━━╱"),
            EmotionName.HAPPY: ("╭━━", "━━╮"),
            EmotionName.THINKING: ("━━╲", "━━╲"),
            EmotionName.WARY: ("━━╲", "╱━━"),
        }.get(expression, ("━━━", "━━━"))

        if blink:
            eyes = ("━━━━", "━━━━")
        else:
            pupil = "◉"
            if gaze < 0:
                eyes = (f"{pupil} ◁", f"{pupil} ◁")
            elif gaze > 0:
                eyes = (f"▷ {pupil}", f"▷ {pupil}")
            else:
                eyes = (f"◇{pupil}◇", f"◇{pupil}◇")

        micro = tick % 41 in {0, 1}
        mouths = {
            EmotionName.CURIOUS: "○",
            EmotionName.SKEPTICAL: "━━━",
            EmotionName.CONFUSED: "◇",
            EmotionName.HAPPY: "╰━━━━╯",
            EmotionName.THINKING: "──",
            EmotionName.SPEAKING: "╭━━━━╮" if tick % 4 < 2 else "╰──╯",
            EmotionName.LISTENING: "──",
            EmotionName.WARY: "━━━",
        }
        mouth = mouths.get(expression, "──" if not micro else "··")
        return {
            "left_brow": brows[0],
            "right_brow": brows[1],
            "left_eye": eyes[0],
            "right_eye": eyes[1],
            "mouth": mouth,
        }

    @staticmethod
    def _unicode_face(features: dict[str, str], offset: int) -> list[str]:
        pad = " " * offset
        inner_width = 31

        def inside(content: str = "") -> str:
            return pad + "     │" + content.center(inner_width) + "│"

        brows = f"{features['left_brow']:<5}{' ' * 11}{features['right_brow']:>5}"
        eyes = f"{features['left_eye']:<5}{' ' * 11}{features['right_eye']:>5}"
        return [
            pad + "            ╭─────────────────────╮",
            pad + "        ╭───╯                     ╰───╮",
            pad + "      ╱                               ╲",
            inside(brows),
            inside(eyes),
            inside("╱╲"),
            inside("╱  ╲"),
            inside("╱ ╲  ╲"),
            inside("╲____╱"),
            inside(),
            inside(features["mouth"]),
            pad + "      ╲                               ╱",
            pad + "        ╲          ╲_______╱        ╱",
            pad + "          ╰──────────┬────────────╯",
            pad + "                     │",
        ]

    @staticmethod
    def _ascii_face(features: dict[str, str], offset: int) -> list[str]:
        pad = " " * offset
        mapping = {
            "╭": "+",
            "╮": "+",
            "╰": "+",
            "╯": "+",
            "━": "-",
            "─": "-",
            "╲": "\\",
            "╱": "/",
            "◇": "o",
            "◉": "O",
            "◁": "<",
            "▷": ">",
            "○": "o",
            "│": "|",
        }

        def clean(value: str) -> str:
            return "".join(mapping.get(char, char) for char in value)

        inner_width = 31

        def inside(content: str = "") -> str:
            return pad + "     |" + clean(content).center(inner_width) + "|"

        brows = f"{clean(features['left_brow']):<5}{' ' * 11}{clean(features['right_brow']):>5}"
        eyes = f"{clean(features['left_eye']):<5}{' ' * 11}{clean(features['right_eye']):>5}"
        return [
            pad + "            +---------------------+",
            pad + "        +---+                     +---+",
            pad + "      /                               \\",
            inside(brows),
            inside(eyes),
            inside("/\\"),
            inside("/  \\"),
            inside("/ \\  \\"),
            inside("\\____/"),
            inside(),
            inside(features["mouth"]),
            pad + "      \\                               /",
            pad + "        \\          \\_______/        /",
            pad + "          +----------+------------+",
            pad + "                     |",
        ]
