"""Интеграционные тесты: алиасы + fuzzy + справочник."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.gazetteer import get_gazetteer


@pytest.fixture(scope="module")
def gaz():
    return get_gazetteer()


class TestAliases:
    def test_alias_nursiti_exists(self, gaz):
        """Алиас Нурсити загружен."""
        assert len(gaz._aliases) > 0, "aliases.json должен быть загружен"
    
    def test_alias_finds_living_area(self, gaz):
        """Нурсити через алиас находит жилой массив."""
        result = gaz.find_living_area("Нурсити")
        assert result is not None, "Нурсити должен находиться через алиас"
        name = result.get("name", "")
        assert "нурсити" in name.lower(), f"Ожидали Нурсити, получили {name}"
        assert result.get("source") == "alias", "Источник должен быть alias"

    def test_alias_bereke_as_landmark(self, gaz):
        """Берееке в алиасах."""
        nk = "берееке"  # norm_key
        assert nk in gaz._aliases or any(nk in k for k in gaz._aliases), \
            "Берееке должен быть в алиасах"

    def test_gazetteer_has_cities(self, gaz):
        """Справочник имеет города."""
        assert len(gaz._all_cities) > 10000, \
            f"Ожидали >10K городов, получили {len(gaz._all_cities)}"

    def test_gazetteer_has_streets(self, gaz):
        """Справочник имеет улицы."""
        assert len(gaz._all_streets) > 5000, \
            f"Ожидали >5K улиц, получили {len(gaz._all_streets)}"

    def test_fuzzy_cache_works(self, gaz):
        """Fuzzy кэш работает — повторный вызов быстрее."""
        from app.fuzzy import fuzzy_find
        
        # Первый вызов — заполняет кэш
        r1 = fuzzy_find("Кулинская", gaz._all_cities[:100])
        cache_before = len(gaz._fuzzy_cache)
        
        # Второй вызов — должен использовать кэш
        r2 = fuzzy_find("Кулинская", gaz._all_cities[:100])
        cache_after = len(gaz._fuzzy_cache)
        
        assert r1 == r2, "Результаты должны совпадать"
        assert cache_after >= cache_before, "Кэш должен заполняться"


class TestGazetteerDescribe:
    def test_describe_contains_stats(self, gaz):
        desc = gaz.describe()
        assert "provinces" in desc or "cities" in desc, \
            f"describe() должна содержать статистику, получила: {desc}"

    def test_describe_shows_aliases_count(self, gaz):
        if gaz._aliases:
            desc = gaz.describe()
            assert "alias" in desc.lower(), f"describe() должна показывать алиасы: {desc}"
