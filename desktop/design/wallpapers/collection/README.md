# Zaod OS built-in wallpapers

Two sets ship in the image:

* **Photographs** downloaded for the OS from Wikimedia Commons. Each is cropped to
  7680x4320 (8K UHD) from a native 8K-class original, so the detail is real.
  These are licensed CC BY-SA or public domain; the attribution below is required
  and is also installed at /usr/share/zaod/licenses/wallpaper-credits.md.
* **Owner set** (`zaod-night-pier`, `zaod-ascension`, `zaod-purple-sunset`,
  `zaod-torii-blossom`, `zaod-alpine-lake`, `zaod-sunset-cabin`, `zaod-golden-road`,
  `zaod-starlit-tree`, `zaod-gold-folds`), supplied by the Zaod OS owner. The
  originals arrived chat-sized, so these are upscaled to 8K - the resolution is 8K,
  the detail is not native. Replace a file with a native 8K version of the same name
  when one exists; nothing else has to change.

A Spider-Man wallpaper was also sent and is deliberately not shipped: it is Marvel
artwork and cannot be redistributed inside an operating-system image.

## Photograph credits

| File | Title | Author | Licence | Source |
| --- | --- | --- | --- | --- |
| `zaod-lake-louise.jpg` | 1 lake louise pano 2019.jpg | Chensiyuan | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:1_lake_louise_pano_2019.jpg |
| `zaod-loch-tummel.jpg` | Foggy Reflections - Loch Tummel.jpg | Eric Kilby | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Foggy_Reflections_-_Loch_Tummel.jpg |
| `zaod-titicaca-dawn.jpg` | Amanecer en el lago Titicaca, Puno, Perú, 2015-08-01, DD 02.JPG | Diego Delso | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Amanecer_en_el_lago_Titicaca,_Puno,_Per%C3%BA,_2015-08-01,_DD_02.JPG |
| `zaod-night-lake.jpg` | Björkljustern 2020-03-22.jpg | Calle Eklund | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Bj%C3%B6rkljustern_2020-03-22.jpg |
| `zaod-khumbu.jpg` | Aerial View of Peaks of Khumbu, Ngozumpa Glacier and Gokyo Lakes.jpg | Megaurab09 | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Aerial_View_of_Peaks_of_Khumbu,_Ngozumpa_Glacier_and_Gokyo_Lakes.jpg |

## Changing it

Control Center → Wallpapers, or `zaod-wallpaper --list` / `zaod-wallpaper NAME`.
The choice is stored in `~/.config/zaod/wallpaper` and survives a restart.
