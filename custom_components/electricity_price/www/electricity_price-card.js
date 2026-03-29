'use strict';

class ElectricityPriceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
  }

  static getConfigElement() {
    return document.createElement('electricity-price-card-editor');
  }

  static getStubConfig() {
    return { device_id: '', day: 'today' };
  }

  setConfig(config) {
    if (!config.device_id && !config.entity) {
      throw new Error('Please select an Electricity Price device.');
    }
    this._config = { day: 'today', ...config };
    if (this._hass) this._render();
  }

  set hass(hass) {
    const prevHass = this._hass;
    this._hass = hass;
    if (!this._config) return;
    const entityId = this._findPriceEntity();
    // Re-render when the resolved entity changes or its state changes.
    if (entityId !== this._priceEntityId || hass.states[entityId] !== prevHass?.states[entityId]) {
      this._priceEntityId = entityId;
      this._render();
    }
  }

  /** Find the entity that carries today_prices / tomorrow_prices for the configured device. */
  _findPriceEntity() {
    if (!this._hass) return null;
    const { states, entities } = this._hass;

    // Legacy configs stored an entity ID directly.
    if (this._config.entity && !this._config.device_id) {
      return this._config.entity;
    }

    const deviceId = this._config.device_id;
    if (entities) {
      // Entity registry available (HA 2022.4+): match by device_id and attribute.
      const eid = Object.keys(entities).find(id =>
        entities[id].device_id === deviceId && states[id]?.attributes.today_prices !== undefined
      );
      return eid || null;
    }

    // Fallback for older HA: find any state with today_prices.
    return Object.keys(states).find(id => states[id]?.attributes.today_prices !== undefined) || null;
  }

  getCardSize() {
    return 4;
  }

  // ─── Main render ────────────────────────────────────────────────────────────

  _render() {
    if (!this._hass || !this._config) return;

    const entityId = this._findPriceEntity();
    const stateObj = entityId ? this._hass.states[entityId] : null;
    const shadow = this.shadowRoot;

    if (!stateObj) {
      shadow.innerHTML = `
        <ha-card>
          <div style="padding:16px;color:var(--error-color,#db4437)">
            No Electricity Price data found. Please select a device.
          </div>
        </ha-card>`;
      return;
    }

    const attrs = stateObj.attributes;
    const todayPrices    = attrs.today_prices    ?? {};
    const tomorrowPrices = attrs.tomorrow_prices  ?? {};
    const thresholds     = attrs.thresholds       ?? [];
    const unit           = attrs.unit             ?? 'c/kWh';
    const tomorrowAvail  = attrs.tomorrow_available ?? (Object.keys(tomorrowPrices).length >= 88);

    const isTomorrow = this._config.day === 'tomorrow';
    const prices     = isTomorrow ? tomorrowPrices : todayPrices;

    // Current UTC key rounded to 15-min boundary, matching Python's _utc_key().
    const currentKey = isTomorrow ? null : (attrs.current_key ?? _currentUtcKey());

    const currentPrice = currentKey !== null ? (todayPrices[currentKey] ?? null) : null;
    const currentLevel = currentPrice !== null ? this._getLevel(currentPrice, thresholds) : null;
    const currentColor = currentPrice !== null ? this._getColor(currentPrice, thresholds) : 'var(--primary-text-color)';

    const title = this._config.title ?? (isTomorrow ? 'Tomorrow' : 'Today');

    if (isTomorrow && !tomorrowAvail) {
      shadow.innerHTML = `
        <ha-card>
          <div style="padding:16px;color:var(--secondary-text-color)">
            Tomorrow's prices are not yet available.
          </div>
        </ha-card>`;
      return;
    }

    const priceDisplay = currentPrice !== null
      ? `${currentPrice.toFixed(2)} ${unit}`
      : `— ${unit}`;

    shadow.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; box-sizing: border-box; }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 10px;
          gap: 8px;
        }
        .title {
          font-size: 0.95em;
          font-weight: 500;
          color: var(--secondary-text-color);
          padding-top: 2px;
        }
        .current { text-align: right; flex-shrink: 0; }
        .current-price {
          font-size: 1.75em;
          font-weight: 700;
          line-height: 1;
          color: ${currentColor};
        }
        .current-level {
          font-size: 0.78em;
          color: var(--secondary-text-color);
          margin-top: 3px;
        }
        .chart { width: 100%; }
        svg { width: 100%; height: auto; display: block; }

        .legend {
          display: flex;
          flex-wrap: wrap;
          gap: 8px 14px;
          margin-top: 10px;
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
        <div class="header">
          <div class="title">${_esc(title)}</div>
          ${!isTomorrow ? `<div class="current">
            <div class="current-price">${_esc(priceDisplay)}</div>
            ${currentLevel ? `<div class="current-level">${_esc(currentLevel)}</div>` : ''}
          </div>` : ''}
        </div>
        <div class="chart">
          ${this._buildChart(prices, thresholds, currentKey, unit)}
        </div>
        <div class="legend">
          ${this._buildLegend(thresholds, unit)}
        </div>
      </ha-card>`;
  }

  // ─── SVG chart ──────────────────────────────────────────────────────────────

  _buildChart(prices, thresholds, currentKey, unit) {
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

    // Helpers.
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

    // Y-axis unit label (rotated).
    const midY = f(MT + CH / 2);
    els.push(
      `<text x="8" y="${midY}" text-anchor="middle" font-size="8"`,
      ` fill="var(--secondary-text-color,#888)"`,
      ` transform="rotate(-90 8 ${midY})">${_esc(unit)}</text>`
    );

    // ── Threshold lines ───────────────────────────────────────────────────────
    thresholds.forEach(t => {
      const v = t.below;
      if (v === null || v === undefined || !isFinite(v)) return;
      if (v <= yMin || v >= yMax) return;
      const y = f(yOf(v));
      els.push(
        `<line x1="${ML}" y1="${y}" x2="${VW - MR}" y2="${y}"`,
        ` stroke="${t.color}" stroke-width="1.2" stroke-dasharray="5,3" opacity="0.8"/>`,
        `<text x="${VW - MR - 3}" y="${f(yOf(v) - 2)}"`,
        ` text-anchor="end" font-size="8" fill="${t.color}" opacity="0.9">${_esc(t.name)}</text>`
      );
    });

    // ── Bars ──────────────────────────────────────────────────────────────────
    bars.forEach((bar, i) => {
      const isCurrent = bar.key === currentKey;
      const color     = this._getColor(bar.price, thresholds);
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

    return `<svg viewBox="0 0 ${VW} ${VH}" xmlns="http://www.w3.org/2000/svg">${els.join('')}</svg>`;
  }

  // ─── Legend ─────────────────────────────────────────────────────────────────

  _buildLegend(thresholds, unit) {
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

  // ─── Threshold helpers ───────────────────────────────────────────────────────

  _getColor(price, thresholds) {
    for (const t of thresholds) {
      if (t.below === null || t.below === undefined || price < t.below) {
        return t.color || '#94a3b8';
      }
    }
    return thresholds.at(-1)?.color || '#94a3b8';
  }

  _getLevel(price, thresholds) {
    for (const t of thresholds) {
      if (t.below === null || t.below === undefined || price < t.below) {
        return t.name;
      }
    }
    return thresholds.at(-1)?.name || '';
  }
}

// ─── Utilities ─────────────────────────────────────────────────────────────────

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

// ─── Visual editor ─────────────────────────────────────────────────────────────
//
// Uses ha-form with a declarative schema — the same mechanism HA's own
// integrations use.  A single element handles entity-picker, select, and text
// inputs without any manual component wiring.

const _EDITOR_SCHEMA = [
  {
    name: 'device_id',
    required: true,
    selector: { device: { integration: 'electricity_price' } },
  },
  {
    name: 'day',
    selector: {
      select: {
        options: [
          { value: 'today',    label: 'Today'    },
          { value: 'tomorrow', label: 'Tomorrow' },
        ],
      },
    },
  },
  {
    name: 'title',
    selector: { text: {} },
  },
];

const _EDITOR_LABELS = { device_id: 'Device', day: 'Day', title: 'Title (optional)' };

class ElectricityPriceCardEditor extends HTMLElement {
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
    this._form.schema = _EDITOR_SCHEMA;
    this._form.computeLabel = (s) => _EDITOR_LABELS[s.name] ?? s.name;
    this._form.addEventListener('value-changed', (ev) => {
      const data = { ...ev.detail.value };
      // Remove title when cleared so the card falls back to its auto title.
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

customElements.define('electricity-price-card-editor', ElectricityPriceCardEditor);

// ─── Registration ───────────────────────────────────────────────────────────────

customElements.define('electricity-price-card', ElectricityPriceCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'electricity-price-card',
  name: 'Electricity Price Chart',
  description: 'ENTSO-E day-ahead electricity price chart with configurable thresholds',
  preview: false,
});
