import pytest

from ecopulse.emissions import EmissionCalculator, FactorStore, UnknownActivityError


@pytest.fixture
def calc():
    return EmissionCalculator(FactorStore())


def test_fixed_factor_scales_with_quantity(calc):
    result = calc.estimate("car_petrol", 10, "IN")
    assert result.co2e_kg == pytest.approx(1.65, abs=0.01)
    assert result.region_used is None  # a petrol car does not depend on the grid
    assert result.category == "transport"


def test_electricity_is_localised(calc):
    india = calc.estimate("electricity_home", 100, "IN")
    uk = calc.estimate("electricity_home", 100, "GB")
    assert india.co2e_kg == pytest.approx(72.7, abs=0.1)
    assert uk.co2e_kg == pytest.approx(23.8, abs=0.1)
    assert india.co2e_kg > uk.co2e_kg


def test_electric_vehicle_uses_the_grid(calc):
    india = calc.estimate("car_ev", 50, "IN")
    brazil = calc.estimate("car_ev", 50, "BR")
    assert india.co2e_kg > brazil.co2e_kg
    assert india.region_used == "IN"


def test_subnational_code_falls_back_to_country(calc):
    result = calc.estimate("electricity_home", 10, "in-up")
    assert result.region_used == "IN"
    assert result.grid_fallback is False


def test_unknown_region_uses_world_average_and_says_so(calc):
    result = calc.estimate("electricity_home", 10, "ZZ")
    assert result.region_used == "GLOBAL"
    assert result.grid_fallback is True


def test_unknown_activity_raises(calc):
    with pytest.raises(UnknownActivityError):
        calc.estimate("teleporter", 5, "IN")


def test_negative_quantity_rejected(calc):
    with pytest.raises(ValueError):
        calc.estimate("bus", -1, "IN")


def test_walking_is_zero(calc):
    assert calc.estimate("walk_cycle", 5, "IN").co2e_kg == 0


def test_every_factor_has_the_fields_the_api_needs():
    store = FactorStore()
    assert len(store.activities()) >= 15
    for factor in store.activities():
        assert factor.source and factor.confidence and factor.unit
