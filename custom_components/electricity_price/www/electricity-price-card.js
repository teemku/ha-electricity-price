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
      return '<p class="no-data">No price data available</p>';
    }

    const prices = slots.map(s => s.price);
    const maxP = Math.max(...prices);
    const minP = Math.min(0, Math.min(...prices));
    const range = (maxP - minP) * 1.15 || 1;

    // Margins scale with height so labels remain readable at any size.
    const mL = Math.max(32, W * 0.08), mB = Math.max(18, H * 0.1), mT = 8, mR = 8;
    const cW = W - mL - mR;
    const cH = H - mB - mT;

    const toY = v => mT + cH * (1 - (v - minP) / range);
    const barW = cW / slots.length;
    const gap = Math.max(0.5, barW * 0.1);

    // X-axis label every N bars to avoid crowding
    const n = slots.length;
    const labelEvery = n > 72 ? 8 : n > 36 ? 4 : n > 12 ? 4 : 2;

    // Y-axis: 5 evenly spaced ticks
    const tickStep = range / 4;
    const yTicks = [0, 1, 2, 3, 4].map(i => minP + i * tickStep);

    const fs = Math.max(8, Math.min(13, H * 0.06)); // font size scales with height

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

    // Bars
    for (let i = 0; i < slots.length; i++) {
      const { utcKey, localLabel, price } = slots[i];
      const x = (mL + i * barW + gap / 2).toFixed(1);
      const w = (barW - gap).toFixed(1);
      const y = toY(price).toFixed(1);
      const h = (toY(minP) - toY(price)).toFixed(1);
      const color = this._priceColor(price, thresholds);
      const isCurrent = utcKey === currentKey;
      const isPast = currentKey && utcKey < currentKey;
      const opacity = isCurrent ? 1 : isPast ? 0.3 : 0.75;

      out += `<rect x="${x}" y="${y}" width="${w}" height="${h}"
        fill="${color}" opacity="${opacity}" rx="1">
        <title>${localLabel} · ${price.toFixed(2)} c/kWh</title>
      </rect>`;

      if (isCurrent) {
        out += `<rect x="${(+x - 1.5).toFixed(1)}" y="${(+y - 1.5).toFixed(1)}"
          width="${(+w + 3).toFixed(1)}" height="${(+h + 1.5).toFixed(1)}"
          fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2" rx="2"/>`;
      }

      if (i % labelEvery === 0) {
        const lx = (mL + (i + 0.5) * barW).toFixed(1);
        out += `<text x="${lx}" y="${(H - fs * 0.3).toFixed(1)}" text-anchor="middle"
          font-size="${fs}" fill="var(--secondary-text-color,#888)">${localLabel}</text>`;
      }
    }

    // Baseline
    const baseY = toY(0).toFixed(1);
    out += `<line x1="${mL}" y1="${baseY}" x2="${W - mR}" y2="${baseY}"
      stroke="var(--secondary-text-color,#888)" stroke-width="0.8"/>`;

    // Unit
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
    const tomorrowDisabled = !tomorrowSlots.length;
    const tab = this._tab;

    const showLegend = this._config.show_legend !== false;
    const legendHtml = showLegend && thresholds.length
      ? `<div class="legend">${thresholds.map(t =>
          `<span class="legend-item">
            <span class="legend-dot" style="background:${t.color}"></span>${t.name}
          </span>`).join('')}</div>`
      : '';

    const title = this._config.title ?? '';
    const showCurrentPrice = this._config.show_current_price !== false;
    const currentPrice = this._entityState?.state;
    const currentPriceColor = currentPrice != null
      ? this._priceColor(parseFloat(currentPrice), thresholds)
      : 'var(--primary-text-color)';
    const currentPriceHtml = showCurrentPrice && currentPrice != null
      ? `<div class="current-price" style="color:${currentPriceColor}">
           ${parseFloat(currentPrice).toFixed(2)}<span class="current-price-unit"> c/kWh</span>
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
        .header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12px; flex-shrink: 0; }
        .title { font-size: 1em; font-weight: 500; color: var(--primary-text-color); }
        .current-price { font-size: 1.4em; font-weight: 600; line-height: 1; }
        .current-price-unit { font-size: 0.55em; font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
        .tabs { display: flex; gap: 6px; margin-bottom: 10px; flex-shrink: 0; }
        .tab {
          padding: 5px 14px; border-radius: 14px; font-size: 0.82em; cursor: pointer;
          border: 1px solid var(--divider-color, rgba(0,0,0,.2)); background: transparent;
          color: var(--secondary-text-color); font-family: inherit; transition: all .15s;
        }
        .tab.active {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
          border-color: var(--primary-color, #03a9f4);
        }
        .tab:disabled { opacity: 0.4; cursor: default; }
        .chart-container { flex: 1; min-height: 0; overflow: hidden; }
        .no-data { text-align: center; padding: 32px 0; color: var(--secondary-text-color); font-size: .9em; margin: 0; }
        .legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; flex-shrink: 0; }
        .legend-item { display: flex; align-items: center; gap: 5px; font-size: .8em; color: var(--secondary-text-color); }
        .legend-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
      </style>
      <ha-card>
        ${title || currentPriceHtml ? `<div class="header"><div class="title">${title}</div>${currentPriceHtml}</div>` : ''}
        <div class="tabs">
          <button class="tab ${tab === 'today' ? 'active' : ''}" data-tab="today">Today</button>
          <button class="tab ${tab === 'tomorrow' ? 'active' : ''}" data-tab="tomorrow"${tomorrowDisabled ? ' disabled' : ''}>Tomorrow</button>
        </div>
        <div class="chart-container"></div>
        ${legendHtml}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll('.tab:not(:disabled)').forEach(btn => {
      btn.addEventListener('click', () => {
        this._tab = btn.dataset.tab;
        this._render();
      });
    });

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

    container.innerHTML = tab === 'tomorrow' && !tomorrowSlots.length
      ? '<p class="no-data">Tomorrow\'s prices are not yet available</p>'
      : this._renderChart(activeSlots, tab === 'today' ? currentKey : '', thresholds, W, H);
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
        <ha-selector id="device" label="Device"></ha-selector>
        <ha-textfield id="title" label="Title (optional)"></ha-textfield>
        <ha-formfield label="Show current price">
          <ha-switch id="current-price"></ha-switch>
        </ha-formfield>
        <ha-formfield label="Show legend">
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

    this.shadowRoot.getElementById('title').value = this._config?.title ?? '';
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
