"""The names of the countries around Serbia, in Serbian Latin: what a visitor reads on a foreign heks.

ISO3 → name, for every country that can touch the map's frame (Serbia's bounding box grown by the 200 km margin).
The frame reaches further than the neighbours proper: its north edge takes in southern Slovakia, its north-east
corner a corner of Ukraine, and its east edge the western tip of the Turkish island Gökçeada.

Serbia and Kosovo are not in the table: they are never another country's neighbour on this map. The boundaries
source skips both (their own sources draw them) and fails, naming the country, when one touches the frame that has
no name here.
"""

SR = {
    "ALB": "Albanija",
    "AUT": "Austrija",
    "BIH": "Bosna i Hercegovina",
    "BGR": "Bugarska",
    "HRV": "Hrvatska",
    "GRC": "Grčka",
    "HUN": "Mađarska",
    "ITA": "Italija",
    "MNE": "Crna Gora",
    "MKD": "Severna Makedonija",
    "ROU": "Rumunija",
    "SVK": "Slovačka",
    "SVN": "Slovenija",
    "TUR": "Turska",
    "UKR": "Ukrajina",
}
