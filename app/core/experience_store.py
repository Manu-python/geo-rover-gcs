from __future__ import annotations

import json
from pathlib import Path

from app.core.experience import (
    ExperienceRecord,
    ExperienceSituation,
    experience_record_from_dict,
    experience_record_to_dict,
)


class ExperienceStore:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()

    def load_all(self) -> list[ExperienceRecord]:
        if not self.path.is_file():
            return []

        records: list[ExperienceRecord] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    records.append(experience_record_from_dict(json.loads(text)))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Invalid experience record at {self.path}:{line_number}: {exc}"
                    ) from exc

        return records

    def append(self, record: ExperienceRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(experience_record_to_dict(record), sort_keys=True))
            file.write("\n")

    def find_similar(
        self,
        current_situation: ExperienceSituation,
        limit: int | None = None,
    ) -> list[tuple[ExperienceRecord, float]]:
        matches: list[tuple[ExperienceRecord, float]] = []
        for record in self.load_all():
            score = _score_similarity(current_situation, record)
            if score > 0:
                matches.append((record, score))

        matches.sort(key=lambda item: item[1], reverse=True)
        if limit is None or limit <= 0:
            return matches
        return matches[:limit]


def _score_similarity(
    current_situation: ExperienceSituation,
    record: ExperienceRecord,
) -> float:
    score = 0.0
    if record.situation.state == current_situation.state:
        score += 0.45
    if record.situation.front_bucket == current_situation.front_bucket:
        score += 0.20
    if record.situation.left_bucket == current_situation.left_bucket:
        score += 0.15
    if record.situation.right_bucket == current_situation.right_bucket:
        score += 0.15
    if record.outcome == "success":
        score += 0.05
    return min(round(score, 6), 1.0)
