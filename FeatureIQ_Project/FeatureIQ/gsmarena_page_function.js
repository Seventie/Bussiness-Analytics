/**
 * FeatureIQ - GSMArena extraction logic for apify/cheerio-scraper
 *
 * Crawl flow (handled by Link selector + Pseudo-URLs, not by this function):
 *   makers.php3  ->  brand pages (samsung-phones-9.php)
 *                ->  brand pagination (samsung-phones-f-9-0-p2.php)
 *                ->  device pages (samsung_galaxy_s24_ultra_5g-12771.php)
 *
 * This function only decides "is this a device page?" and extracts RAW text.
 * All numeric parsing (mAh, GB, MP, inches, currency) happens in Python so you
 * can fix parsing bugs without re-scraping.
 */
async function pageFunction(context) {
    const { $, request, log } = context;
    const url = request.url;

    const isBrandPage =
        /makers\.php3$/i.test(url) ||
        /-phones(-f)?-\d+(-\d+-p\d+)?\.php$/i.test(url);
    const isDevicePage = /\/[a-z0-9_]+-\d+\.php$/i.test(url);

    // ---- 1) Listing pages: nothing to save, but detect soft-blocks ----------
    if (isBrandPage) {
        if (!$('div.makers li, div.st-text a').length) {
            // HTTP 200 but no listing markup => challenge/ban page. Retry on a new IP.
            throw new Error(`Empty listing (probably blocked): ${url}`);
        }
        return null; // null => nothing pushed to the dataset
    }

    if (!isDevicePage) return null;

    // ---- 2) Device page -------------------------------------------------------
    const titleEl = $('h1.specs-phone-name-title');
    if (!titleEl.length) {
        throw new Error(`Device page without title (probably blocked): ${url}`);
    }

    const clean = (s) => {
        const t = (s || '').replace(/\s+/g, ' ').trim();
        return t.length ? t : null;
    };
    // <td data-spec="..."> cells in the big spec tables
    const spec = (key) => clean($(`td[data-spec="${key}"]`).first().text());
    // spotlight/highlight spans at the top of the page
    const hl = (key) => clean($(`[data-spec="${key}"]`).first().text());

    const deviceName = clean(titleEl.text());

    // Brand = first word of the title, except known two-word brands
    const twoWordBrands = ['Sony Ericsson'];
    let brand = deviceName.split(' ')[0];
    for (const b of twoWordBrands) {
        if (deviceName.startsWith(b + ' ')) brand = b;
    }
    const model = clean(deviceName.slice(brand.length));

    return {
        url,
        brand,
        model_name: model,
        device_name: deviceName,

        // --- the 8 required fields (raw text) ---
        price_raw: spec('price'),                 // "$ 799.99 / EUR 899 / Rs 79,999" or "About 250 EUR"
        battery_raw: spec('batdescription1'),     // "Li-Po 5000 mAh, non-removable"
        battery_hl: hl('batsize-hl'),             // "5000"
        memory_raw: spec('internalmemory'),       // "256GB 12GB RAM, 512GB 12GB RAM"
        main_camera_raw: spec('cam1modules'),     // "200 MP, f/1.7, 24mm (wide) ..."
        camera_hl: hl('camerapixels-hl'),         // "200"
        display_size_raw: spec('displaysize'),    // "6.8 inches, 113.5 cm2 ..."
        display_size_hl: hl('displaysize-hl'),    // 6.8"

        // --- extras that help filter / segment in FeatureIQ ---
        announced: spec('year'),
        status: spec('status'),
        os: spec('os'),
        chipset: spec('chipset'),
        network_tech: spec('nettech'),
        popularity_raw: clean($('li.help-popularity').text()),  // hits = demand proxy
        fans_raw: clean($('li.help-fans').text()),

        scraped_at: new Date().toISOString(),
    };
}
