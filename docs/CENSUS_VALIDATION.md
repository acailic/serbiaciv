# Census 2022 processing validation

Processed the ten cached RZS workbooks with `python -m pipeline process census --offline`. Counts refer to this cached snapshot; source URLs, retrieval times and checksums are recorded in the raw-cache manifest.

- 173 census units and 4,720 settlement rows; 4,704 settlement rows matched a territory ID.
- The only non-Kosovo territorial units without their own census row are Novi Sad (80284) and Petrovaradin (80519); the census has the Grad Novi Sad (89010) aggregate.
- The four sample populations were Grad Beograd 1,681,405, Grad Novi Sad 368,967, Grad Niš 249,501, and Aleksandrovac 22,069. Across all units with comparable data, age-group sums, ethnicity totals, and religion totals matched population.
- Area indent is not consistently hierarchical; rows are matched by territory name and parent in workbook order. Four explicit aliases are validated exactly once per workbook.
- The following settlement names did not match the territory tree. They retain their census data and parent unit with a null settlement ID; no spelling or territorial match was guessed.

- `('Београд (Врачар)', 'RS110', '70114')`
- `('Београд (Савски Венац)', 'RS110', '70220')`
- `('Београд (Стари Град)', 'RS110', '70246')`
- `('Војвода Зимонић', 'RS124', '80195')`
- `('Засавица 1', 'RS127', '80403')`
- `('Засавица 2', 'RS127', '80403')`
- `('Севојно', 'RS211', '71366')`
- `('Доброљупци', 'RS216', '70017')`
- `('Горње Пунушевце', 'RS228', '70432')`
- `('Доње Пунушевце', 'RS228', '70432')`
- `('Клашнице', 'RS228', '70432')`
- `('Рибинце', 'RS228', '70432')`
- `('Мрча', 'RS229', '70688')`
- `('Паваштица', 'RS229', '70688')`
- `('Прекорађа', 'RS229', '70688')`
- `('Трпезе', 'RS229', '70688')`

The municipality age workbook also contains an unmatched `Београд (Звездара)` sub-area row; it is not treated as a separate municipality. These findings do not establish that the complete map build is valid.
