const TRANSLATIONS = {
  en: {
    today: 'Today',
    tomorrow: 'Tomorrow',
    avg: 'daily avg',
    current_price_label: 'current price',
    next_price_label: 'next',
    no_data: 'No price data available',
    tomorrow_unavailable: "Tomorrow's prices are not yet available. Available in ~{h} h.",
    editor_device: 'Device',
    editor_title: 'Title (optional)',
    editor_visible_tabs: 'Day selection',
    editor_tabs_both: 'Show as tabs',
    editor_tabs_today: 'Today only',
    editor_tabs_tomorrow: 'Tomorrow only',
    editor_show_next_price: 'Show next slot price',
    editor_show_average_line: 'Show average price line',
    editor_show_price_tier: 'Show price level',
    editor_show_current_price: 'Show current price',
    editor_show_legend: 'Show legend',
  },
  fi: {
    today: 'Tänään',
    tomorrow: 'Huomenna',
    avg: 'päivän keskiarvo',
    current_price_label: 'nykyinen hinta',
    next_price_label: 'seuraava',
    no_data: 'Hintadata ei saatavilla',
    tomorrow_unavailable: 'Huomisen hinnat eivät ole vielä saatavilla. Saatavilla ~{h} h kuluttua.',
    editor_device: 'Laite',
    editor_title: 'Otsikko (valinnainen)',
    editor_visible_tabs: 'Päivän valinta',
    editor_tabs_both: 'Näytä välilehtinä',
    editor_tabs_today: 'Vain tänään',
    editor_tabs_tomorrow: 'Vain huomenna',
    editor_show_next_price: 'Näytä seuraava hinta',
    editor_show_average_line: 'Näytä keskihintaviiva',
    editor_show_price_tier: 'Näytä hintataso',
    editor_show_current_price: 'Näytä nykyinen hinta',
    editor_show_legend: 'Näytä kaavion selite',
  },
};

function contrastColor(hex) {
  // Returns black or white depending on which has better contrast against hex.
  const c = hex.replace('#', '');
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  // Perceived luminance (WCAG formula)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.55 ? '#000000' : '#ffffff';
}

function t(hass, key) {
  const lang = hass?.language?.split('-')[0] ?? 'en';
  return (TRANSLATIONS[lang] ?? TRANSLATIONS.en)[key] ?? TRANSLATIONS.en[key] ?? key;
}

class ElectricityPriceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._tab = 'today';
    this._resizeObserver = null;
  }

  disconnectedCallback() {
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
  }

  static getConfigElement() {
    return document.createElement('electricity-price-card-editor');
  }

  static getStubConfig() {
    return { device_id: '' };
  }

  setConfig(config) {
    if (!config.device_id) {
      throw new Error('electricity-price-card: device_id is required');
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _findPriceEntity() {
    if (!this._hass || !this._config?.device_id) return null;
    for (const entity of Object.values(this._hass.entities || {})) {
      if (entity.device_id !== this._config.device_id) continue;
      const state = this._hass.states[entity.entity_id];
      if (state?.attributes?.today_prices !== undefined) return state;
    }
    return null;
  }

  _priceColor(price, thresholds) {
    if (!thresholds?.length) return 'var(--primary-color, #03a9f4)';
    for (const t of thresholds) {
      if (t.below == null || price < t.below) return t.color || '#94a3b8';
    }
    return thresholds[thresholds.length - 1]?.color || '#94a3b8';
  }

  // Convert {utcISO: price} to [{utcKey, localLabel, price}] sorted by local time.
  _toSlots(prices) {
    return Object.entries(prices)
      .map(([utcKey, price]) => {
        const d = new Date(utcKey);
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        return { utcKey, localLabel: `${hh}:${mm}`, price, date: d };
      })
      .sort((a, b) => a.date - b.date);
  }

  _currentUtcKey(resolutionMinutes) {
    const now = new Date();
    const res = resolutionMinutes || 60;
    const snapped = Math.floor(now.getUTCMinutes() / res) * res;
    const d = new Date(Date.UTC(
      now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
      now.getUTCHours(), snapped, 0,
    ));
    return `${d.toISOString().slice(0, 19)}Z`;
  }

  _renderChart(slots, currentKey, thresholds, W, H) {
    if (!slots.length) {
      return `<p class="no-data">${t(this._hass, 'no_data')}</p>`;
    }

    const prices = slots.map(s => s.price);
    const maxP = Math.max(...prices);
    const minP = Math.min(0, Math.min(...prices));
    const range = (maxP - minP) * 1.15 || 1;

    const mL = Math.max(32, W * 0.08), mB = Math.max(18, H * 0.1), mT = 8, mR = 8;
    const cW = W - mL - mR;
    const cH = H - mB - mT;
    const fs = Math.max(8, Math.min(13, H * 0.06));

    const toX = i => mL + (i / slots.length) * cW;
    const toY = v => mT + cH * (1 - (v - minP) / range);
    const baseY = toY(minP);

    // Y-axis ticks
    const yTicks = [0, 1, 2, 3, 4].map(i => minP + (range / 4) * i);

    // X-axis: label at hour boundaries (minute === 0), skip if too crowded
    const slotWidthPx = cW / slots.length;
    const minLabelSpacing = fs * 5;
    const labelEverySlots = Math.max(1, Math.ceil(minLabelSpacing / slotWidthPx));

    let out = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"
      width="${W}" height="${H}" overflow="visible">`;

    // Gridlines + Y labels
    for (const tick of yTicks) {
      const y = toY(tick).toFixed(1);
      out += `<line x1="${mL}" y1="${y}" x2="${W - mR}" y2="${y}"
        stroke="var(--divider-color,rgba(0,0,0,.12))" stroke-width="0.5"/>`;
      out += `<text x="${(mL - 3).toFixed(1)}" y="${(+y + fs * 0.4).toFixed(1)}" text-anchor="end"
        font-size="${fs}" fill="var(--secondary-text-color,#888)">${tick.toFixed(1)}</text>`;
    }

    // Average price line
    if (this._config.show_average_line !== false) {
      const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
      const avgY = toY(avg).toFixed(1);
      out += `<line x1="${mL}" y1="${avgY}" x2="${(W - mR).toFixed(1)}" y2="${avgY}"
        stroke="var(--secondary-text-color,#888)" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>`;
      out += `<text x="${(mL - 3).toFixed(1)}" y="${(+avgY + fs * 0.4).toFixed(1)}" text-anchor="end"
        font-size="${(fs * 0.8).toFixed(1)}" fill="var(--secondary-text-color,#888)" opacity="0.8">${avg.toFixed(1)}</text>`;
    }

    // Filled area under each slot, coloured by tier
    for (let i = 0; i < slots.length; i++) {
      const { utcKey, price } = slots[i];
      const x1 = toX(i), x2 = toX(i + 1);
      const y = toY(price);
      const color = this._priceColor(price, thresholds);
      const isPast = currentKey && utcKey < currentKey;
      out += `<rect x="${x1.toFixed(1)}" y="${y.toFixed(1)}"
        width="${(x2 - x1).toFixed(1)}" height="${(baseY - y).toFixed(1)}"
        fill="${color}" opacity="${isPast ? 0.15 : 0.35}"/>`;
    }

    // Step line — one horizontal segment per slot, vertical connectors between
    let path = `M ${toX(0).toFixed(1)} ${toY(slots[0].price).toFixed(1)}`;
    for (let i = 0; i < slots.length; i++) {
      const x2 = toX(i + 1);
      path += ` H ${x2.toFixed(1)}`;
      if (i + 1 < slots.length) path += ` V ${toY(slots[i + 1].price).toFixed(1)}`;
    }

    // Draw past portion dimmed, future at full opacity
    const currentIdx = currentKey ? slots.findIndex(s => s.utcKey === currentKey) : -1;
    if (currentIdx > 0) {
      const splitX = toX(currentIdx).toFixed(1);
      out += `<clipPath id="past"><rect x="${mL}" y="${mT}" width="${splitX - mL}" height="${cH}"/></clipPath>`;
      out += `<clipPath id="future"><rect x="${splitX}" y="${mT}" width="${W - mR - splitX}" height="${cH}"/></clipPath>`;
      out += `<path d="${path}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2" opacity="0.35" clip-path="url(#past)"/>`;
      out += `<path d="${path}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2" clip-path="url(#future)"/>`;
    } else {
      out += `<path d="${path}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2"/>`;
    }

    // Current time marker
    if (currentIdx >= 0) {
      const cx = toX(currentIdx).toFixed(1);
      out += `<line x1="${cx}" y1="${mT}" x2="${cx}" y2="${baseY.toFixed(1)}"
        stroke="var(--primary-color,#03a9f4)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.7"/>`;
      // Dot on the line at current price
      const cy = toY(slots[currentIdx].price).toFixed(1);
      out += `<circle cx="${cx}" cy="${cy}" r="4" fill="var(--primary-color,#03a9f4)"/>`;
    }

    // X-axis labels
    for (let i = 0; i < slots.length; i += labelEverySlots) {
      const lx = toX(i).toFixed(1);
      out += `<text x="${lx}" y="${(H - fs * 0.3).toFixed(1)}" text-anchor="middle"
        font-size="${fs}" fill="var(--secondary-text-color,#888)">${slots[i].localLabel}</text>`;
    }

    // Baseline
    out += `<line x1="${mL}" y1="${baseY.toFixed(1)}" x2="${W - mR}" y2="${baseY.toFixed(1)}"
      stroke="var(--secondary-text-color,#888)" stroke-width="0.8"/>`;

    // Unit label
    out += `<text x="${(mL - 3).toFixed(1)}" y="${(mT + fs).toFixed(1)}" text-anchor="end"
      font-size="${(fs * 0.85).toFixed(1)}" fill="var(--secondary-text-color,#888)">c/kWh</text>`;

    out += '</svg>';
    return out;
  }

  _render() {
    if (!this._config || !this._hass) return;

    this._entityState = this._findPriceEntity();
    const attrs = this._entityState?.attributes ?? {};
    const tomorrowPrices = attrs.tomorrow_prices ?? {};
    const thresholds = attrs.thresholds ?? [];

    const tomorrowSlots = this._toSlots(tomorrowPrices);
    const tabsMode = this._config.tabs ?? 'both';
    if (tabsMode !== 'both') this._tab = tabsMode;
    const tab = this._tab;
    const showTabs = tabsMode === 'both';
    const tomorrowDisabled = !tomorrowSlots.length;

    const lang = this._hass?.language?.split('-')[0] ?? 'en';
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const fmtWeekday = d => new Intl.DateTimeFormat(lang, { weekday: 'short' }).format(d);
    const fmtDay = d => new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short' }).format(d);

    const showLegend = this._config.show_legend !== false;
    const legendHtml = showLegend && thresholds.length
      ? `<div class="legend">${thresholds.map(t =>
          `<span class="legend-item">
            <span class="legend-dot" style="background:${t.color}"></span>${t.name}
          </span>`).join('')}</div>`
      : '';

    const title = this._config.title ?? '';
    const showCurrentPrice = this._config.show_current_price !== false;

    let displayPrice = null;
    if (tab === 'tomorrow' && tomorrowSlots.length) {
      const vals = tomorrowSlots.map(s => s.price);
      displayPrice = vals.reduce((a, b) => a + b, 0) / vals.length;
    } else if (this._entityState?.state != null) {
      displayPrice = parseFloat(this._entityState.state);
    }

    const displayPriceColor = displayPrice != null
      ? this._priceColor(displayPrice, thresholds)
      : 'var(--primary-text-color)';

    const showPriceTier = this._config.show_price_tier === true;
    const priceTier = displayPrice != null
      ? thresholds.find(th => th.below == null || displayPrice < th.below) ?? thresholds[thresholds.length - 1]
      : null;
    const tierBadgeHtml = showPriceTier && priceTier
      ? `<div class="tier-badge" style="background:${priceTier.color};color:${contrastColor(priceTier.color)}">${priceTier.name}</div>`
      : '';

    const priceValueHtml = showCurrentPrice && displayPrice != null
      ? `<span style="color:${displayPriceColor}">${displayPrice.toFixed(2)}<span class="current-price-unit"> c/kWh</span></span>` : '';
    const priceLabelHtml = showCurrentPrice && displayPrice != null
      ? `<div class="current-price-label">${t(this._hass, tab === 'tomorrow' ? 'avg' : 'current_price_label')}</div>` : '';

    // Next slot indicator — replaces current price label when enabled
    const showNextPrice = this._config.show_next_price === true;
    let nextSlotHtml = '';
    if (showNextPrice && tab === 'today' && displayPrice != null) {
      const todayPrices = attrs.today_prices ?? {};
      const resMin = attrs.resolution_minutes ?? 60;
      const currentKey = this._currentUtcKey(resMin);
      const todaySlots = this._toSlots(todayPrices);
      const currentIdx = todaySlots.findIndex(s => s.utcKey === currentKey);
      const nextSlot = todaySlots[currentIdx + 1]
        ?? this._toSlots(attrs.tomorrow_prices ?? {})[0];
      if (nextSlot) {
        const diff = nextSlot.price - displayPrice;
        const triangle = diff > 0.005 ? '▲' : diff < -0.005 ? '▼' : '▶';
        const triangleColor = diff > 0.005 ? 'var(--error-color,#ef4444)' : diff < -0.005 ? 'var(--success-color,#22c55e)' : 'var(--secondary-text-color,#888)';
        const nextColor = this._priceColor(nextSlot.price, thresholds);
        nextSlotHtml = `<div class="next-price">
          <span style="color:${triangleColor}">${triangle}</span>
          <span style="color:${nextColor}">${nextSlot.price.toFixed(2)}</span><span class="next-price-unit"> c/kWh</span>
        </div>`;
      }
    }

    const belowPriceHtml = showNextPrice && nextSlotHtml ? nextSlotHtml : priceLabelHtml;

    const currentPriceHtml = tierBadgeHtml || priceValueHtml || nextSlotHtml
      ? `<div class="current-price">
           <div class="price-row">${tierBadgeHtml}${priceValueHtml}</div>
           ${belowPriceHtml}
         </div>`
      : '';

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; }
        ha-card {
          padding: 16px 16px 12px;
          height: 100%;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
        }
        .title { font-size: 1.2em; font-weight: 500; color: var(--primary-text-color); margin-bottom: 8px; flex-shrink: 0; }
        .header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 10px; flex-shrink: 0; }
        .current-price { font-size: 1.4em; font-weight: 600; line-height: 1; text-align: right; }
        .price-row { display: flex; align-items: center; justify-content: flex-end; gap: 8px; line-height: 1; }
        .current-price-unit { font-size: 0.55em; font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
        .current-price-label { font-size: 0.55em; font-weight: 400; color: var(--secondary-text-color); margin-top: 6px; }
        .next-price { font-size: 0.55em; font-weight: 500; display: flex; align-items: center; justify-content: flex-end; gap: 3px; margin-top: 6px; }
        .next-price-unit { color: var(--secondary-text-color); font-weight: 400; }
        .tier-badge { display: inline-block; font-size: 0.6em; font-weight: 600; color: #fff;
          padding: 3px 10px; border-radius: 99px; letter-spacing: 0.03em; }
        .day-selector { margin-bottom: 10px; flex-shrink: 0; }
        .day-pill { display: flex; background: var(--input-fill-color, rgba(120,120,120,0.1)); border-radius: 10px; padding: 3px; gap: 2px; }
        .day-opt { flex: 1; border: none; background: transparent; border-radius: 8px; padding: 7px 12px; font-size: 0.85em; font-weight: 500; cursor: pointer; color: var(--secondary-text-color); font-family: inherit; transition: background .15s, color .15s, box-shadow .15s; }
        .day-opt.active { background: var(--card-background-color, #1c1c1e); color: var(--primary-text-color); box-shadow: 0 1px 4px rgba(0,0,0,0.25); }
        .day-opt:disabled { opacity: 0.35; cursor: default; }
        .chart-container { flex: 1; min-height: 0; overflow: hidden; }
        .no-data { text-align: center; padding: 32px 0; color: var(--secondary-text-color); font-size: .9em; margin: 0; }
        .legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; flex-shrink: 0; }
        .legend-item { display: flex; align-items: center; gap: 5px; font-size: .8em; color: var(--secondary-text-color); }
        .legend-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
      </style>
      <ha-card>
        <div class="header">
          <div>${title ? `<div class="title">${title}</div>` : ''}</div>
          ${currentPriceHtml}
        </div>
        ${showTabs ? `<div class="day-selector">
          <div class="day-pill">
            <button class="day-opt ${tab === 'today' ? 'active' : ''}" data-tab="today">${t(this._hass, 'today')}</button>
            <button class="day-opt ${tab === 'tomorrow' ? 'active' : ''}" data-tab="tomorrow"${tomorrowDisabled ? ' disabled' : ''}>${t(this._hass, 'tomorrow')}</button>
          </div>
        </div>` : ''}
        <div class="chart-container"></div>
        ${legendHtml}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll('.day-opt:not(:disabled)').forEach(btn => {
      btn.addEventListener('click', () => {
        this._tab = btn.dataset.tab;
        this._render();
      });
    });

    if (tabsMode === 'both') {
      const chartEl = this.shadowRoot.querySelector('.chart-container');
      let touchStartX = 0;
      chartEl.addEventListener('touchstart', e => {
        touchStartX = e.touches[0].clientX;
      }, { passive: true });
      chartEl.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(dx) < 40) return;
        if (dx < 0 && !tomorrowDisabled) { this._tab = 'tomorrow'; this._render(); }
        else if (dx > 0) { this._tab = 'today'; this._render(); }
      }, { passive: true });
    }

    this._setupResizeObserver();
  }

  _setupResizeObserver() {
    this._resizeObserver?.disconnect();
    const container = this.shadowRoot.querySelector('.chart-container');
    if (!container) return;
    this._resizeObserver = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) this._drawChart(container, Math.round(width), Math.round(height));
    });
    this._resizeObserver.observe(container);
  }

  _drawChart(container, W, H) {
    const attrs = this._entityState?.attributes ?? {};
    const todayPrices = attrs.today_prices ?? {};
    const tomorrowPrices = attrs.tomorrow_prices ?? {};
    const thresholds = attrs.thresholds ?? [];
    const resMin = attrs.resolution_minutes ?? 60;
    const todaySlots = this._toSlots(todayPrices);
    const tomorrowSlots = this._toSlots(tomorrowPrices);
    const currentKey = this._currentUtcKey(resMin);
    const tab = this._tab;
    const activeSlots = tab === 'today' ? todaySlots : tomorrowSlots;

    if (tab === 'tomorrow' && !tomorrowSlots.length) {
      // Estimate hours until ~13:00 CET (UTC+1) when prices are typically published.
      const now = new Date();
      const publishUTC = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 12, 0, 0));
      if (now >= publishUTC) publishUTC.setUTCDate(publishUTC.getUTCDate() + 1);
      const hoursLeft = Math.ceil((publishUTC - now) / 3_600_000);
      const msg = t(this._hass, 'tomorrow_unavailable').replace('{h}', hoursLeft);
      container.innerHTML = `<p class="no-data">${msg}</p>`;
    } else {
      container.innerHTML = this._renderChart(activeSlots, tab === 'today' ? currentKey : '', thresholds, W, H);
    }
  }
}

customElements.define('electricity-price-card', ElectricityPriceCard);


class ElectricityPriceCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  setConfig(config) {
    this._config = { ...config };
    if (!this._built) this._build();
    this._update();
  }

  _build() {
    this._built = true;
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        .editor { display: flex; flex-direction: column; gap: 16px; }
      </style>
      <div class="editor">
        <ha-selector id="device" label="${t(this._hass, 'editor_device')}"></ha-selector>
        <ha-textfield id="title" label="${t(this._hass, 'editor_title')}"></ha-textfield>
        <ha-selector id="tabs" label="${t(this._hass, 'editor_visible_tabs')}"></ha-selector>
        <ha-formfield label="${t(this._hass, 'editor_show_next_price')}">
          <ha-switch id="next-price"></ha-switch>
        </ha-formfield>
        <ha-formfield label="${t(this._hass, 'editor_show_average_line')}">
          <ha-switch id="average-line"></ha-switch>
        </ha-formfield>
        <ha-formfield label="${t(this._hass, 'editor_show_price_tier')}">
          <ha-switch id="price-tier"></ha-switch>
        </ha-formfield>
        <ha-formfield label="${t(this._hass, 'editor_show_current_price')}">
          <ha-switch id="current-price"></ha-switch>
        </ha-formfield>
        <ha-formfield label="${t(this._hass, 'editor_show_legend')}">
          <ha-switch id="legend"></ha-switch>
        </ha-formfield>
      </div>
    `;

    this.shadowRoot.getElementById('device').addEventListener('value-changed', e => {
      this._config = { ...this._config, device_id: e.detail.value };
      this._fire();
    });

    this.shadowRoot.getElementById('title').addEventListener('change', e => {
      this._config = { ...this._config, title: e.target.value };
      this._fire();
    });

    this.shadowRoot.getElementById('tabs').addEventListener('value-changed', e => {
      this._config = { ...this._config, tabs: e.detail.value };
      this._fire();
    });

    this.shadowRoot.getElementById('next-price').addEventListener('change', e => {
      this._config = { ...this._config, show_next_price: e.target.checked };
      this._fire();
    });

    this.shadowRoot.getElementById('average-line').addEventListener('change', e => {
      this._config = { ...this._config, show_average_line: e.target.checked };
      this._fire();
    });

    this.shadowRoot.getElementById('price-tier').addEventListener('change', e => {
      this._config = { ...this._config, show_price_tier: e.target.checked };
      this._fire();
    });

    this.shadowRoot.getElementById('current-price').addEventListener('change', e => {
      this._config = { ...this._config, show_current_price: e.target.checked };
      this._fire();
    });

    this.shadowRoot.getElementById('legend').addEventListener('change', e => {
      this._config = { ...this._config, show_legend: e.target.checked };
      this._fire();
    });
  }

  _update() {
    if (!this._built) return;

    const deviceSelector = this.shadowRoot.getElementById('device');
    if (this._hass) deviceSelector.hass = this._hass;
    deviceSelector.selector = { device: { integration: 'electricity_price' } };
    deviceSelector.value = this._config?.device_id ?? '';

    const titleField = this.shadowRoot.getElementById('title');
    if (titleField !== this.shadowRoot.activeElement) {
      titleField.value = this._config?.title ?? '';
    }

    const tabsSelector = this.shadowRoot.getElementById('tabs');
    if (this._hass) tabsSelector.hass = this._hass;
    tabsSelector.label = t(this._hass, 'editor_visible_tabs');
    tabsSelector.selector = {
      select: {
        options: [
          { value: 'both',     label: t(this._hass, 'editor_tabs_both') },
          { value: 'today',    label: t(this._hass, 'editor_tabs_today') },
          { value: 'tomorrow', label: t(this._hass, 'editor_tabs_tomorrow') },
        ],
      },
    };
    tabsSelector.value = this._config?.tabs ?? 'both';

    this.shadowRoot.getElementById('next-price').checked = this._config?.show_next_price === true;
    this.shadowRoot.getElementById('average-line').checked = this._config?.show_average_line !== false;
    this.shadowRoot.getElementById('price-tier').checked = this._config?.show_price_tier === true;
    this.shadowRoot.getElementById('current-price').checked = this._config?.show_current_price !== false;
    this.shadowRoot.getElementById('legend').checked = this._config?.show_legend !== false;
  }

  _fire() {
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    }));
  }
}

customElements.define('electricity-price-card-editor', ElectricityPriceCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'electricity-price-card',
  name: 'Electricity Price',
  description: "Shows today's and tomorrow's electricity prices as a bar chart",
  preview: false,
});
