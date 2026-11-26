# OverKill Hill P³ website images

## Website icons and previews

- The web manifest uses the 192 × 192 and 512 × 512 MurderBird v2 PNGs in [favicons](favicons/), with separate maskable variants. The header uses [the 96 × 96 nav mark](murderbird-v2-icon-nav-96.png).
- The browser icon links use MurderBird v2 PNG and ICO versions. The root [favicon.svg](../../favicon.svg) contains the legacy OverKill Hill vector mark. It is a separate design from the v2 MurderBird raster icons.

## Blueprint Edition

| File | Dimensions | Usage |
| --- | --- | --- |
| [Blueprint banner](overkill-hill-blueprint-hero-2400.png) | 2400 × 1350 PNG | Alternate homepage hero art. The responsive MurderBird v2 picture remains the default for homepage editions. |
| [Blueprint feature](overkill-hill-blueprint-feature-1200.png) | 1200 × 1200 PNG | Perched MurderBird artwork for feature cards and previews. |
| [Blueprint foreground](overkill-hill-blueprint-foreground.png) | 1536 × 1024 RGBA PNG | Two separated subjects on transparent pixels for placement over a background. |
| [Blueprint social preview](og/overkill-hill-blueprint-share-1200x630.jpg) | 1200 × 630 JPEG | Open Graph and Twitter image for the US English homepage. |

The banner and social crop use the CRT-left stalking composition, based on
the title-stenciled wide artwork in [the image library](library/). The square
is a title-removal edit of the perched square in that library. The transparent
foreground retains the original branch illustration, with the bird on the
left. The delivery images carry no embedded title.

For an informative banner, use “A mechanical MurderBird stalks a green CRT
across a striped blueprint.” For the square, use “A riveted MurderBird perches
on a green CRT.” For the foreground, use “A mechanical bird raises one talon
as it approaches a CRT computer.” If the illustration is decorative in
context, use `alt="" role="presentation"`. Keep visible typography in HTML.
The US homepage `.stripe-bg` grid uses CSS gradients.
