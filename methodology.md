# Methodology

## The calculation

For every activity:

```
co2e_kg = quantity × factor
```

There are two kinds of factor.

**Fixed**: a flat number, for example a petrol car at 0.165 kg CO2e per km.

**Electricity-based**: kWh used per unit, multiplied by the grid intensity of the user's region.

```
factor = kwh_per_unit × grid_kg_co2e_per_kwh(region)
```

Home electricity is 1 kWh per kWh. An electric car is assumed to use 0.15 kWh per km, a train 0.04 kWh per passenger-km. So the same trip or the same bill lands differently depending on where the user lives.

## Localisation

`data/grid_intensity.json` holds kg CO2e per kWh by region. A region code is resolved in this order:

1. The exact code (`IN-UP`)
2. The country part (`IN`)
3. The world average (`GLOBAL`), with `grid_fallback: true` in the response so the caller knows

India is one national grid (the regional grids were merged in 2013), so India has a single figure. To add state-level values, add entries such as `IN-UP` to the file. Ember publishes sub-national data for Indian states.

## Data sources

| Data | Value | Source |
|---|---|---|
| India grid | 0.727 kg CO2/kWh (FY2023-24, weighted average including renewables) | Central Electricity Authority (CEA), CO2 Baseline Database for the Indian Power Sector |
| US, UK, China, Canada, Brazil, Australia, Bangladesh, world | 2023 carbon intensity of electricity generation | Ember and the Energy Institute, via Our World in Data |
| Petrol and diesel cars, two-wheelers | Typical fuel factors (petrol about 2.31 kg CO2/L, diesel about 2.68 kg CO2/L) divided by an assumed fuel economy | Published fuel factors, assumptions listed in `emission_factors.json` |
| Food | Per-kg footprints multiplied by assumed portion sizes | Poore & Nemecek (2018), via Our World in Data |
| Other transport, LPG, waste | Rounded typical values | Noted per entry in `emission_factors.json` |

Every entry in `data/emission_factors.json` carries a `source`, a `note` and a `confidence` label:

- `derived`: calculated from a published factor plus a stated assumption
- `approximate`: a rounded typical value in line with published ranges
- `assumption`: a rough estimate built on a stated portion size or usage assumption; treat as low confidence

`GET /factors` returns all of this, so users can see how each number was reached.

## Limitations

- These are estimates for personal awareness. They are not audit-grade and should not be used for official reporting without checking each factor.
- Fuel factors are tailpipe only. Fuel production and vehicle manufacture are not counted.
- Grid figures are for generation. Transmission and distribution losses are not added, which understates emissions from electricity you actually consume.
- The India figure counts CO2 only, while the other regions' figures are CO2e. The two bases are close but not identical.
- Food factors depend heavily on portion size and where the food was produced.
- Grid intensity is a yearly average. It does not vary by time of day or season.
- The habit-change `share` values in `data/swaps.json` (for example "30% of car km could go by bus") are assumptions about what is realistic, not measurements.

## Updating the data

1. Edit the JSON file. Keep `source`, `note` and `confidence` filled in.
2. Run `pytest`. The tests check that every factor loads and that key numbers behave as expected.
3. Old log entries keep the factor they were logged with. Only new entries use the new number.
