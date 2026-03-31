'use strict';

// ─── Shared helpers ─────────────────────────────────────────────────────────

/** Format a number to 1 decimal place for SVG coordinates. */
function f(n) { return n.toFixed(1); }

/** Zero-pad a number to 2 digits. */
function pad(h) { return String(h).padStart(2, '0'); }

/** Escape HTML special characters for safe inline output. */
function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Compute the UTC ISO key for the current 15-min slot, matching Python's _utc_key(). */
function _currentUtcKey() {
  const ms15 = 15 * 60 * 1000;
  const rounded = new Date(Math.floor(Date.now() / ms15) * ms15);
  return rounded.toISOString().slice(0, 19) + 'Z';
}

function _getColor(price, thresholds) {
  for (const t of thresholds) {
    if (t.below === null || t.below === undefined || price < t.below) {
      return t.color || '#94a3b8';
    }
  }
  return thresholds.at(-1)?.color || '#94a3b8';
}

function _getLevel(price, thresholds) {
  for (const t of thresholds) {
    if (t.below === null || t.below === undefined || price < t.below) {
      return t.name;
    }
  }
  return thresholds.at(-1)?.name || '';
}

function _buildChart(prices, thresholds, currentKey, unit) {
  const bars = Object.keys(prices).sort().map(key => ({ key, price: prices[key] }));
  const totalBars = bars.length;

  // SVG viewport dimensions and margins.
  const VW = 600, VH = 230;
  const ML = 50, MR = 16, MT = 22, MB = 30;
  const CW = VW - ML - MR;
  const CH = VH - MT - MB;

  if (totalBars === 0) {
    return `<svg viewBox="0 0 ${VW} ${VH}">` +
      `<text x="${VW / 2}" y="${VH / 2}" text-anchor="middle" ` +
      `font-size="13" fill="var(--secondary-text-color,#888)">No data available</text></svg>`;
  }

  // Determine Y-axis range.
  const validPrices = bars.map(b => b.price);
  const thresholdBounds = thresholds
    .map(t => t.below)
    .filter(v => v !== null && v !== undefined && isFinite(v));

  const rawMax = Math.max(...validPrices, ...thresholdBounds);
  const rawMin = Math.min(0, ...validPrices);
  const yMax   = rawMax * 1.12;
  const yMin   = rawMin < 0 ? rawMin * 1.1 : 0;
  const yRange = (yMax - yMin) || 1;

  const barGroupW = CW / totalBars;
  const barW      = Math.max(barGroupW * 0.78, 1.5);
  const barPad    = (barGroupW - barW) / 2;

  const xOf  = i => ML + i * barGroupW + barPad;
  const yOf  = v => MT + CH - ((v - yMin) / yRange) * CH;
  const hOf  = v => Math.max(((v - yMin) / yRange) * CH, 1);

  const els = [];

  // ── Y-axis grid lines and labels ──────────────────────────────────────────
  const TICK_COUNT = 5;
  for (let i = 0; i <= TICK_COUNT; i++) {
    const v = yMin + (yRange * i) / TICK_COUNT;
    const y = yOf(v);
    els.push(
      `<line x1="${ML}" y1="${f(y)}" x2="${VW - MR}" y2="${f(y)}"`,
      ` stroke="var(--divider-color,#e0e0e0)" stroke-width="0.5"/>`,
      `<text x="${ML - 4}" y="${f(y + 3.5)}" text-anchor="end"`,
      ` font-size="9" fill="var(--secondary-text-color,#888)">${v.toFixed(1)}</text>`
    );
  }

  // Y-axis unit label (top, right-aligned with scale numbers).
  els.push(
    `<text x="${ML - 4}" y="${MT - 12}" text-anchor="end" font-size="9"`,
    ` fill="var(--secondary-text-color,#888)">${_esc(unit)}</text>`
  );

  // ── Threshold lines ───────────────────────────────────────────────────────
  thresholds.forEach(t => {
    const v = t.below;
    if (v === null || v === undefined || !isFinite(v)) return;
    if (v <= yMin || v >= yMax) return;
    const y = f(yOf(v));
    els.push(
      `<line x1="${ML}" y1="${y}" x2="${VW - MR}" y2="${y}"`,
      ` stroke="${t.color}" stroke-width="1.2" stroke-dasharray="5,3" opacity="0.8"/>`
    );
  });

  // ── Bars ──────────────────────────────────────────────────────────────────
  bars.forEach((bar, i) => {
    const isCurrent = bar.key === currentKey;
    const color     = _getColor(bar.price, thresholds);
    const opacity   = isCurrent ? 1.0 : 0.85;
    const x  = f(xOf(i));
    const y  = f(yOf(bar.price));
    const bw = f(barW);
    const bh = f(hOf(bar.price));

    const localTime = new Date(bar.key);
    const hh = localTime.getHours();
    const mm = localTime.getMinutes();
    const tooltip = `${pad(hh)}:${pad(mm)} — ${bar.price.toFixed(2)} ${unit}`;

    const stroke = isCurrent
      ? `stroke="var(--card-background-color,#fff)" stroke-width="1.5"`
      : '';

    els.push(
      `<rect x="${x}" y="${y}" width="${bw}" height="${bh}"`,
      ` fill="${color}" opacity="${opacity}" rx="1" ${stroke}>`,
      `<title>${_esc(tooltip)}</title>`,
      `</rect>`
    );

    // Small triangle above the current slot as a position marker.
    if (isCurrent) {
      const cx  = f(xOf(i) + barW / 2);
      const ty  = f(yOf(bar.price) - 4);
      const hl  = 4;
      const pts = `${cx},${ty} ${f(parseFloat(cx) - hl)},${f(parseFloat(ty) - hl * 1.5)} ${f(parseFloat(cx) + hl)},${f(parseFloat(ty) - hl * 1.5)}`;
      els.push(`<polygon points="${pts}" fill="${color}"/>`);
    }
  });

  // ── X-axis line ───────────────────────────────────────────────────────────
  els.push(
    `<line x1="${ML}" y1="${MT + CH}" x2="${VW - MR}" y2="${MT + CH}"`,
    ` stroke="var(--divider-color,#e0e0e0)" stroke-width="1"/>`
  );

  // ── X-axis labels every 6 hours ───────────────────────────────────────────
  bars.forEach((bar, i) => {
    const localTime = new Date(bar.key);
    if (localTime.getHours() % 6 !== 0 || localTime.getMinutes() !== 0) return;
    const lx = f(xOf(i) + barW / 2);
    els.push(
      `<text x="${lx}" y="${MT + CH + 13}" text-anchor="middle"`,
      ` font-size="9" fill="var(--secondary-text-color,#888)">${pad(localTime.getHours())}</text>`
    );
  });

  // ── Zero line (only when prices can be negative) ──────────────────────────
  if (yMin < 0) {
    const zy = f(yOf(0));
    els.push(
      `<line x1="${ML}" y1="${zy}" x2="${VW - MR}" y2="${zy}"`,
      ` stroke="var(--secondary-text-color,#888)" stroke-width="0.5" stroke-dasharray="2,2"/>`
    );
  }

  return `<svg viewBox="0 0 ${VW} ${VH}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">${els.join('')}</svg>`;
}

function _buildLegend(thresholds, unit) {
  return thresholds.map(t => {
    const label = t.below !== null && t.below !== undefined
      ? `${_esc(t.name)} (&lt;${t.below})`
      : _esc(t.name);
    return `<div class="legend-item">
      <div class="legend-swatch" style="background:${t.color}"></div>
      <span>${label}</span>
    </div>`;
  }).join('');
}

class ElectricityPriceChartCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._tab = 'today';
    this._priceEntityId = null;
  }

  static getConfigElement() {
    return document.createElement('electricity-price-chart-card-editor');
  }

  static getStubConfig() {
    return { device_id: '' };
  }

  setConfig(config) {
    if (!config.device_id && !config.entity) {
      throw new Error('Please select an Electricity Price device.');
    }
    this._config = config;
    if (this._hass) this._render();
  }

  set hass(hass) {
    const prevHass = this._hass;
    this._hass = hass;
    if (!this._config) return;
    const entityId = this._resolveEntity();
    if (entityId !== this._priceEntityId || hass.states[entityId] !== prevHass?.states[entityId]) {
      this._priceEntityId = entityId;
      this._render();
    }
  }

  getCardSize() {
    return 5;
  }

  _resolveEntity() {
    if (!this._hass) return null;
    const { states, entities } = this._hass;
    if (this._config.entity && !this._config.device_id) return this._config.entity;
    const deviceId = this._config.device_id;
    if (entities) {
      return Object.keys(entities).find(id =>
        entities[id].device_id === deviceId &&
        states[id]?.attributes.today_prices !== undefined
      ) ?? null;
    }
    return Object.keys(states).find(id =>
      states[id]?.attributes.today_prices !== undefined
    ) ?? null;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const shadow = this.shadowRoot;
    const stateObj = this._priceEntityId ? this._hass.states[this._priceEntityId] : null;

    if (!stateObj) {
      shadow.innerHTML = `
        <ha-card>
          <div style="padding:16px;color:var(--error-color,#db4437)">
            No Electricity Price data found. Please select a device.
          </div>
        </ha-card>`;
      return;
    }

    const attrs          = stateObj.attributes;
    const todayPrices    = attrs.today_prices    ?? {};
    const tomorrowPrices = attrs.tomorrow_prices  ?? {};
    const thresholds     = attrs.thresholds       ?? [];
    const unit           = attrs.unit             ?? 'c/kWh';
    const tomorrowAvail  = attrs.tomorrow_available ??
      (Object.keys(tomorrowPrices).length >= 88);

    // Config options — all default to the previous behaviour when not set.
    const days             = this._config.days             ?? 'both';
    const showTitle        = this._config.show_title        !== false;
    const showCurrentPrice = this._config.show_current_price !== false;
    const showLegend       = this._config.show_legend       !== false;
    const showTabs         = days === 'both';

    // When a single day is forced via config, override the active tab.
    if (days === 'today')    this._tab = 'today';
    if (days === 'tomorrow') this._tab = 'tomorrow';

    // Snap back to today if tomorrow becomes unavailable while on that tab.
    if (this._tab === 'tomorrow' && !tomorrowAvail) {
      this._tab = 'today';
    }

    const isToday    = this._tab === 'today';
    const prices     = isToday ? todayPrices : tomorrowPrices;
    const currentKey = isToday ? (attrs.current_key ?? _currentUtcKey()) : null;

    const currentPrice = currentKey !== null ? (todayPrices[currentKey] ?? null) : null;
    const currentColor = currentPrice !== null
      ? _getColor(currentPrice, thresholds)
      : 'var(--primary-text-color)';
    const currentLevel = currentPrice !== null ? _getLevel(currentPrice, thresholds) : null;

    const tomorrowValues = Object.values(tomorrowPrices);
    const tomorrowAvg = tomorrowValues.length > 0
      ? tomorrowValues.reduce((s, v) => s + v, 0) / tomorrowValues.length
      : null;

    const title = this._config.title ?? 'Electricity Price';

    // Rebuild the card structure. The chart element is detached by innerHTML
    // but its reference is preserved in this._chartEl and re-appended below.
    shadow.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
        }
        ha-card {
          flex: 1;
          display: flex;
          flex-direction: column;
          padding: 0;
          box-sizing: border-box;
          width: 100%;
          min-height: 200px;
        }
        .content-wrapper {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-height: 0;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 8px;
          padding: 18px 20px 0;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .header-left {
          display: flex;
          flex-direction: column;
          min-width: 0;
        }
        .title {
          font-size: 1.4em;
          font-weight: 500;
          color: var(--secondary-text-color);
          margin-bottom: 8px;
        }
        .current {
          text-align: right;
          flex-shrink: 0;
          padding: 0 0 14px 16px;
        }
        .current-price {
          font-size: 1.4em;
          font-weight: 500;
          line-height: 1;
          color: ${currentColor};
        }
        .price-unit {
          font-size: 0.65em;
          font-weight: 400;
        }
        .current-level {
          font-size: 0.78em;
          color: var(--secondary-text-color);
          margin-top: 2px;
        }
        .tabs {
          display: flex;
          margin-bottom: -1px;
          margin-left: -12px;
        }
        .tab {
          padding: 6px 12px;
          cursor: pointer;
          font-size: 1em;
          font-weight: 500;
          color: var(--secondary-text-color);
          border-bottom: 2px solid transparent;
          user-select: none;
          transition: color 0.15s, border-color 0.15s;
        }
        .tab:hover:not(.disabled):not(.active) {
          color: var(--primary-text-color);
        }
        .tab.active {
          color: var(--primary-color);
          border-bottom-color: var(--primary-color);
        }
        .tab.disabled {
          opacity: 0.38;
          cursor: not-allowed;
          pointer-events: none;
        }
        .chart {
          flex: 1;
          min-height: 150px;
          width: 100%;
          padding: 8px 0 0;
        }
        svg { width: 100%; height: 100%; display: block; }
        .legend {
          display: flex;
          flex-wrap: wrap;
          gap: 8px 14px;
          padding: 8px 16px 12px;
        }
        .legend-item {
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 0.75em;
          color: var(--secondary-text-color);
        }
        .legend-swatch {
          width: 10px;
          height: 10px;
          border-radius: 2px;
          flex-shrink: 0;
        }
      </style>
      <ha-card>
        <div class="content-wrapper">
          <div class="card-header">
            <div class="header-left">
              ${showTitle ? `<div class="title">${_esc(title)}</div>` : ''}
              ${showTabs ? `
              <div class="tabs">
                <div class="tab${isToday ? ' active' : ''}" data-tab="today">Today</div>
                <div class="tab${!isToday ? ' active' : ''}${!tomorrowAvail ? ' disabled' : ''}" data-tab="tomorrow">Tomorrow</div>
              </div>` : ''}
            </div>
            ${showCurrentPrice && isToday && currentPrice !== null ? `
              <div class="current">
                <div class="current-price">${currentPrice.toFixed(2)} <span class="price-unit">${_esc(unit)}</span></div>
                ${currentLevel ? `<div class="current-level">${_esc(currentLevel)}</div>` : ''}
              </div>` : ''}
            ${showCurrentPrice && !isToday && tomorrowAvg !== null ? `
              <div class="current">
                <div class="current-price">${tomorrowAvg.toFixed(2)} <span class="price-unit">${_esc(unit)}</span></div>
                <div class="current-level">avg</div>
              </div>` : ''}
          </div>
          <div class="chart">
            ${_buildChart(prices, thresholds, currentKey, unit)}
          </div>
        </div>
        ${showLegend ? `
        <div class="legend">
          ${_buildLegend(thresholds, unit)}
        </div>` : ''}
      </ha-card>`;

    // Attach tab-switch listeners after the DOM is written.
    shadow.querySelectorAll('.tab:not(.disabled)').forEach(el => {
      el.addEventListener('click', () => {
        if (el.dataset.tab !== this._tab) {
          this._tab = el.dataset.tab;
          this._render();
        }
      });
    });
  }

}

// ─── Visual editor ────────────────────────────────────────────────────────────

const _CHART_EDITOR_SCHEMA = [
  {
    name: 'device_id',
    required: true,
    selector: { device: { integration: 'electricity_price' } },
  },
  {
    name: 'title',
    selector: { text: {} },
  },
  {
    name: 'days',
    selector: {
      select: {
        options: [
          { value: 'both',     label: 'Today & Tomorrow' },
          { value: 'today',    label: 'Today only'       },
          { value: 'tomorrow', label: 'Tomorrow only'    },
        ],
      },
    },
  },
  {
    name: 'show_title',
    selector: { boolean: {} },
  },
  {
    name: 'show_current_price',
    selector: { boolean: {} },
  },
  {
    name: 'show_legend',
    selector: { boolean: {} },
  },
];

const _CHART_EDITOR_LABELS = {
  device_id:           'Device',
  title:               'Title (optional)',
  days:                'Show days',
  show_title:          'Show title',
  show_current_price:  'Show current price',
  show_legend:         'Show color labels',
};

class ElectricityPriceChartCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    if (this._form) this._form.data = config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._form) {
      this._build();
    } else {
      this._form.hass = hass;
    }
  }

  _build() {
    this._form = document.createElement('ha-form');
    this._form.hass   = this._hass;
    this._form.data   = this._config || {};
    this._form.schema = _CHART_EDITOR_SCHEMA;
    this._form.computeLabel = (s) => _CHART_EDITOR_LABELS[s.name] ?? s.name;
    this._form.addEventListener('value-changed', (ev) => {
      const data = { ...ev.detail.value };
      if (!data.title) delete data.title;
      this._dispatch(data);
    });
    this.appendChild(this._form);
  }

  _dispatch(config) {
    this._config = config;
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
  }
}

// ─── Registration ────────────────────────────────────────────────────────────

customElements.define('electricity-price-chart-card-editor', ElectricityPriceChartCardEditor);
customElements.define('electricity-price-chart-card', ElectricityPriceChartCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'electricity-price-chart-card',
  name: 'Electricity Price Chart',
  description: 'Displays electricity spot prices for today and tomorrow.',
  preview: false,
});
