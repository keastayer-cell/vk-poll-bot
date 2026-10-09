from __future__ import annotations

from functools import lru_cache
from itertools import combinations
from math import lcm

from .ratings import format_rating, rating_units, valid_rating
from .text_tables import player_row


def name_key(name: str) -> str:
    return " ".join(sorted(name.casefold().replace("ё", "е").split()))


def find_player(players: dict, query: str) -> str:
    if query in players:
        return query
    matches = [key for key, p in players.items()
               if any(name_key(name) == name_key(query)
                      for name in [p["name"], *p.get("aliases", [])])]
    if len(matches) > 1:
        raise ValueError("Есть тёзки. Укажите VK ID из /players.")
    if not matches:
        raise ValueError(f"Не найден игрок: {query}")
    return matches[0]


def add_alias(players: dict, query: str, alias: str) -> str:
    key = find_player(players, query)
    alias = " ".join(alias.split())
    if not alias:
        raise ValueError("Укажите дополнительное имя")
    for other_key, player in players.items():
        if other_key != key and (
            alias == other_key or any(name_key(name) == name_key(alias)
                                     for name in [player["name"], *player.get("aliases", [])])
        ):
            raise ValueError("Это имя уже относится к другому игроку. Используйте ФИО или VK ID.")
    player = players[key]
    if not any(name_key(name) == name_key(alias)
               for name in [player["name"], *player.get("aliases", [])]):
        player.setdefault("aliases", []).append(alias)
    return key


def poll_players(poll: dict, players: dict) -> list[dict]:
    result = []
    seen = set()
    entries = [(key, v["name"]) for key, v in poll.get("voters", {}).items()
               if v.get("choice") == "yes"]
    entries += [(None, v["label"]) for v in poll.get("manual_yes_voters", {}).values()]
    for key, name in entries:
        if key is None:
            key = find_player(players, name)
        player = players.get(key, {})
        position = player.get("position")
        if position not in {"field", "goalkeeper"}:
            raise ValueError(f"Не задана роль: {name}. Админ: /position {key} полевой|вратарь")
        rating = player.get("rating")
        if position == "field" and not valid_rating(rating):
            raise ValueError(f"Не заполнен рейтинг: {name}. Админ: /rating {key} 1–10")
        if key in seen:
            raise ValueError(f"Игрок записан дважды: {name}. Уберите лишний +1.")
        seen.add(key)
        result.append({"id": key, "name": player.get("name", name), "rating": rating,
                       "position": position})
    return result


def balanced_teams(players: list[dict], team_size: int = 5) -> list[list[dict]]:
    if team_size not in {4, 5} or len(players) not in {2 * team_size, 3 * team_size}:
        raise ValueError("Нужны две или три равные команды.")
    candidates = []
    minimum_spread = None
    indices = tuple(range(len(players)))
    units = tuple(rating_units(p["rating"]) for p in players)
    # Fix the first player in each group to avoid permutations of identical partitions.
    for tail in combinations(indices[1:], team_size - 1):
        first = (0,) + tail
        remaining = tuple(i for i in indices if i not in first)
        second_choices = (
            [remaining] if len(remaining) == team_size else
            [(remaining[0],) + c for c in combinations(remaining[1:], team_size - 1)]
        )
        for second in second_choices:
            third = tuple(i for i in remaining if i not in second)
            groups = [first, second] + ([third] if third else [])
            totals = [sum(units[i] for i in group) for group in groups]
            spread = max(totals) - min(totals)
            if minimum_spread is None or spread < minimum_spread:
                minimum_spread = spread
                candidates = [candidate for candidate in candidates
                              if candidate[0] <= minimum_spread + 20]
            if spread > minimum_spread + 20:
                continue
            profiles = [sorted((units[i] for i in group), reverse=True)
                        for group in groups]
            # Compare strongest with strongest, second with second, etc. This penalizes
            # concentration of stars/weak players even when the totals happen to match.
            profile_cost = sum(
                (profiles[a][rank] - profiles[b][rank]) ** 2
                for a in range(len(groups)) for b in range(a + 1, len(groups))
                for rank in range(team_size)
            )
            candidates.append((spread, profile_cost, sum(t * t for t in totals), groups))
    _, _, _, best_groups = min(candidates, key=lambda c: (c[1], c[0], c[2]))
    return [[players[i] for i in group] for group in best_groups]


def balanced_five_four_four(players: list[dict]) -> list[list[dict]]:
    if len(players) != 13:
        raise ValueError("Для схемы 5 + 4 + 4 нужны 13 полевых")
    indices = tuple(range(13))
    units = tuple(rating_units(p["rating"]) for p in players)
    candidates = []
    minimum_spread = None

    @lru_cache(maxsize=None)
    def metrics(group):
        ratings = sorted((units[i] for i in group), reverse=True)
        # Twenty quantiles compare all players in unequal-sized teams fairly.
        profile = tuple(r for r in ratings for _ in range(20 // len(group)))
        average_scaled = sum(ratings) * (20 // len(group))
        return average_scaled, profile

    for five in combinations(indices, 5):
        remaining = tuple(i for i in indices if i not in five)
        for tail in combinations(remaining[1:], 3):
            first_four = (remaining[0],) + tail
            second_four = tuple(i for i in remaining if i not in first_four)
            groups = [five, first_four, second_four]
            values = [metrics(group) for group in groups]
            averages = [value[0] for value in values]
            # The five-player side must also be at least as strong per player.
            if averages[0] < max(averages[1:]):
                continue
            spread = max(averages) - min(averages)
            if minimum_spread is None or spread < minimum_spread:
                minimum_spread = spread
                candidates = [c for c in candidates if c[0] <= minimum_spread + 100]
            # Same half-a-rating-point tolerance as two points per four-player side.
            if spread > minimum_spread + 100:
                continue
            profile_cost = sum(
                (values[a][1][rank] - values[b][1][rank]) ** 2
                for a in range(3) for b in range(a + 1, 3) for rank in range(20)
            )
            candidates.append((spread, profile_cost, sum(a * a for a in averages), groups))
    _, _, _, best_groups = min(candidates, key=lambda c: (c[1], c[0], c[2]))
    return [[players[i] for i in group] for group in best_groups]


def balanced_with_substitutes(players: list[dict]) -> list[list[dict]]:
    """Balance two squads, with the larger squad at least as strong per player."""
    if len(players) not in {9, 11}:
        raise ValueError("Для двух неравных составов нужны 9 или 11 полевых")
    large_size = (len(players) + 1) // 2
    small_size = len(players) // 2
    scale = lcm(large_size, small_size)
    indices = tuple(range(len(players)))
    units = tuple(rating_units(p["rating"]) for p in players)
    candidates = []
    minimum_spread = None
    for large in combinations(indices, large_size):
        small = tuple(i for i in indices if i not in large)
        groups = [large, small]
        profiles = [tuple(r for r in sorted(
            (units[i] for i in group), reverse=True
        ) for _ in range(scale // len(group))) for group in groups]
        averages = [sum(profile) for profile in profiles]
        if averages[0] < averages[1]:
            continue
        spread = averages[0] - averages[1]
        if minimum_spread is None or spread < minimum_spread:
            minimum_spread = spread
            candidates = [c for c in candidates if c[0] <= minimum_spread + scale * 5]
        if spread > minimum_spread + scale * 5:
            continue
        profile_cost = sum((a - b) ** 2 for a, b in zip(*profiles))
        candidates.append((spread, profile_cost, groups))
    _, _, best_groups = min(candidates, key=lambda c: (c[1], c[0]))
    return [[players[i] for i in group] for group in best_groups]


def teams_text(poll: dict, players: dict, *, lower_is_stronger: bool = False) -> str:
    total = sum(v.get("choice") == "yes" for v in poll.get("voters", {}).values())
    total += len(poll.get("manual_yes_voters", {}))
    if total < 10:
        return f"Записалось {total}. Для распределения нужны минимум 10 человек, включая вратарей."
    if not 10 <= total <= 15:
        return f"Записалось {total}. Пока поддерживаем от 10 до 15 записавшихся."
    roster = poll_players(poll, players)
    keepers = [p for p in roster if p["position"] == "goalkeeper"]
    fields = [p for p in roster if p["position"] == "field"]
    if lower_is_stronger:
        for player in fields:
            if player["rating"] > 4:
                raise ValueError(
                    f"Обновите рейтинг по шкале 1–4: {player['name']}. "
                    "1 — сильнейшие, 4 — слабейшие."
                )
    original_ratings = {p["id"]: p["rating"] for p in fields}
    if lower_is_stronger:
        # Negation preserves exact differences and makes lower ratings stronger
        # for the existing sum, profile and unequal-team balancing rules.
        fields = [{**p, "rating": -p["rating"]} for p in fields]
    if len(keepers) not in {2, 3} or not 8 <= len(fields) <= 13:
        return ("Нужны 2 или 3 вратаря и от 8 до 13 полевых. "
                f"Сейчас игроков: {total}, вратарей: {len(keepers)}. Проверьте роли игроков.")
    if len(fields) == 13:
        teams = balanced_five_four_four(fields)
    elif len(fields) in {8, 12}:
        teams = balanced_teams(fields, team_size=4)
    elif len(fields) == 10:
        teams = balanced_teams(fields, team_size=5)
    else:
        teams = balanced_with_substitutes(fields)
    sections = []
    for number, team in enumerate(teams, 1):
        team = [{**p, "rating": original_ratings[p["id"]]} for p in team]
        ordered = sorted(team, key=lambda p: (
            p["rating"] if lower_is_stronger else -p["rating"], p["name"]
        ))
        total_rating = sum(p["rating"] for p in team)
        sections.append(
            f"⚽ КОМАНДА {number} · {len(team)} полевых\n"
            f"На поле: 4 · Замены: {len(team) - 4}\n"
            f"Сумма {format_rating(total_rating)} · "
            f"Средний всего состава {total_rating / len(team):.2f}".replace(".", ",") + "\n" +
            "Рейтинг │ ФИО\n────────────────────\n"
            "Основной состав\n" +
            "\n".join(player_row(p) for p in ordered[:4]) +
            ("\n\nЗамены\n" + "\n".join(player_row(p) for p in ordered[4:])
             if len(ordered) > 4 else "")
        )
    sections.append("🧤 Вратари (распределите сами):\n" +
                    "\n".join(player_row(p) for p in keepers))
    return "\n\n".join(sections)
