# Reviewed city positions

The four positions in `pipeline/data/city_positions.csv` come from the `gis_osm_places_free_1` layer in the
cached Geofabrik Serbia extract, retrieved 2026-11-26. They are used when a named settlement cannot be placed by
the 5 km municipality grid. The banner still takes a land hex belonging to the city's own municipality or its
constituent municipalities.

| City | RZS ID | OSM ID | Longitude | Latitude | Reason |
|---|---:|---:|---:|---:|---|
| Smederevo | 71099 | 359219458 | 20.9271115 | 44.6651048 | The 5 km cell containing the point is owned by Kovin, across the Danube, since the grid was fitted to the 1:1 M district file. |
| Beograd | 79014 | 60571493 | 20.4568974 | 44.8178131 | Stari grad has no hex centre at this resolution; OSM labels the place as `national_capital`. |
| Niš | 79022 | 100890898 | 21.8959232 | 43.3211301 | Census borough settlement names differ from OSM's city name. |
| Bačka Palanka | 80063 | 1647188835 | 19.3829401 | 45.2501002 | The 5 km cell containing the point is classified as foreign land at the border. |

Source: `https://download.geofabrik.de/europe/serbia-latest-free.shp.zip`, cached SHA-256
`9f130c3db06f6c5ad054ef88a57946ddee56e187f4d6df2287954b40b135ba84`.
