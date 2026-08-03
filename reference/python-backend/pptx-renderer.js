#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

const EMU_PER_INCH = 914400;
const PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
let currentPptx = null;
const SLIDE_W = 10;
const SLIDE_H = 5.625;

const BUILT_IN_TEMPLATES = {
  venture_blueprint: {
    name: 'Venture Blueprint',
    description: 'Premium pitch and business deck with bold left-rail titles, editorial image zones, and investor-grade evidence layouts.',
    background: 'F7F4EE',
    surface: 'FFFCF7',
    ink: '173042',
    muted: '6B7280',
    accent: '143C5A',
    accent2: 'E4572E',
    accent3: '2FBF71',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  aetheria_modern: {
    name: 'Aetheria Modern',
    description: 'Clean editorial deck for AI strategy and product narratives.',
    background: 'F5F6F0',
    surface: 'FFFFFF',
    ink: '17202A',
    muted: '5A6474',
    accent: '1B5299',
    accent2: 'E8553D',
    accent3: '1A936F',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  executive: {
    name: 'Executive Boardroom',
    description: 'Refined boardroom aesthetic with crisp data hierarchy.',
    background: 'FAF9F5',
    surface: 'FFFFFF',
    ink: '111827',
    muted: '5F6672',
    accent: '0D6B5E',
    accent2: 'C2590A',
    accent3: '1D5BBF',
    fontFace: 'Aptos',
    headingFace: 'Georgia',
  },
  startup_pitch: {
    name: 'Startup Pitch',
    description: 'High-contrast dark deck with bold metrics for investors.',
    background: '0C1524',
    surface: '162036',
    ink: 'F4F5F7',
    muted: 'B0BCCD',
    accent: '60C3F7',
    accent2: 'F48FB1',
    accent3: '81E6A9',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  academic: {
    name: 'Academic Research',
    description: 'Formal scholarly layout with readable evidence and citations.',
    background: 'FFFFFF',
    surface: 'F0F4FA',
    ink: '1E293B',
    muted: '5C6B7F',
    accent: '1749B8',
    accent2: '6D28D9',
    accent3: '047857',
    fontFace: 'Aptos',
    headingFace: 'Cambria',
  },
  creative_portfolio: {
    name: 'Creative Portfolio',
    description: 'Bold expressive deck with vibrant gradients and asymmetric layouts.',
    background: '1A1025',
    surface: '261438',
    ink: 'F8F0FF',
    muted: 'C4A8E0',
    accent: 'FF6B6B',
    accent2: 'C084FC',
    accent3: '4ADE80',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  minimal_zen: {
    name: 'Minimal Zen',
    description: 'Ultra-clean whitespace design with restrained single-accent palette.',
    background: 'FAFAFA',
    surface: 'F4F4F5',
    ink: '18181B',
    muted: '71717A',
    accent: '6366F1',
    accent2: 'A1A1AA',
    accent3: '6366F1',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  tech_dark: {
    name: 'Tech Neon',
    description: 'Dark engineering theme with electric neon accents and sharp edges.',
    background: '0A0E17',
    surface: '121A28',
    ink: 'E8ECF2',
    muted: '8899AA',
    accent: '00E5FF',
    accent2: 'FF3D71',
    accent3: '00E096',
    fontFace: 'Aptos',
    headingFace: 'Aptos Display',
  },
  corporate_gradient: {
    name: 'Corporate Horizon',
    description: 'Professional gradient-rich deck with structured visual hierarchy.',
    background: 'F8FAFC',
    surface: 'FFFFFF',
    ink: '0F172A',
    muted: '5B6578',
    accent: '0F4C81',
    accent2: 'E07A2F',
    accent3: '2E8B57',
    fontFace: 'Aptos',
    headingFace: 'Georgia',
  },
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function writeJson(value) {
  process.stdout.write(JSON.stringify(value));
}

function normalizeText(value, fallback = '') {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map((item) => normalizeText(item)).filter(Boolean).join('\n');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function cleanBullets(value) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeText(item).replace(/^[\s•*-]+/, '').trim()).filter(Boolean);
  }
  return normalizeText(value)
    .split(/\r?\n|;/)
    .map((line) => line.replace(/^[\s•*-]+/, '').trim())
    .filter(Boolean);
}

function safeColor(value, fallback) {
  const text = String(value || '').replace('#', '').trim();
  return /^[0-9a-f]{6}$/i.test(text) ? text.toUpperCase() : fallback;
}

function pickTemplate(name) {
  return BUILT_IN_TEMPLATES[name] || BUILT_IN_TEMPLATES.aetheria_modern;
}

function isDarkTemplate(template) {
  const color = safeColor(template.background, 'FFFFFF');
  const r = parseInt(color.slice(0, 2), 16);
  const g = parseInt(color.slice(2, 4), 16);
  const b = parseInt(color.slice(4, 6), 16);
  return ((r * 299 + g * 587 + b * 114) / 1000) < 128;
}

function hexToRgb(color) {
  const safe = safeColor(color, '000000');
  return {
    r: parseInt(safe.slice(0, 2), 16),
    g: parseInt(safe.slice(2, 4), 16),
    b: parseInt(safe.slice(4, 6), 16),
  };
}

function rgbToHex({ r, g, b }) {
  return [r, g, b].map((value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function mixColor(color, target, amount = 0.5) {
  const a = hexToRgb(color);
  const b = hexToRgb(target);
  return rgbToHex({
    r: a.r + (b.r - a.r) * amount,
    g: a.g + (b.g - a.g) * amount,
    b: a.b + (b.b - a.b) * amount,
  });
}

function boxesOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function textLength(value) {
  return normalizeText(value).replace(/\s+/g, ' ').trim().length;
}

function estimateTextCapacity(box, fontSize = 10, opts = {}) {
  const lineHeight = (fontSize / 72) * (opts.lineHeight || 1.18);
  const charWidth = (fontSize / 72) * (opts.bold ? 0.58 : 0.52);
  const lines = Math.max(1, Math.floor(box.h / Math.max(lineHeight, 0.08)));
  const charsPerLine = Math.max(4, Math.floor(box.w / Math.max(charWidth, 0.04)));
  return Math.floor(lines * charsPerLine * (opts.fit === 'shrink' ? 1.18 : 1));
}

function createLayoutAudit(slideIndex, slideData) {
  return {
    slide_index: slideIndex,
    title: normalizeText(slideData.title || `Slide ${slideIndex}`),
    regions: [],
    warnings: [],
  };
}

function auditRegion(audit, region) {
  if (!audit || !region) return;
  const normalized = {
    role: region.role || 'region',
    kind: region.kind || 'shape',
    x: Number(region.x || 0),
    y: Number(region.y || 0),
    w: Number(region.w || 0),
    h: Number(region.h || 0),
    protected: region.protected !== false,
  };
  if (normalized.x < -0.01 || normalized.y < -0.01 || normalized.x + normalized.w > SLIDE_W + 0.01 || normalized.y + normalized.h > SLIDE_H + 0.01) {
    audit.warnings.push({
      type: 'out_of_bounds',
      severity: 'error',
      role: normalized.role,
      message: `${normalized.role} extends outside the slide canvas.`,
    });
  }
  if (region.kind === 'text') {
    const chars = textLength(region.text);
    const capacity = estimateTextCapacity(normalized, region.fontSize || 10, region);
    if (chars > capacity) {
      audit.warnings.push({
        type: 'text_overflow',
        severity: chars > capacity * 1.35 ? 'error' : 'warning',
        role: normalized.role,
        message: `${normalized.role} may overflow: ${chars} chars for roughly ${capacity} chars of space.`,
      });
    }
  }
  for (const existing of audit.regions) {
    const collisionRelevant = normalized.protected && existing.protected && normalized.kind !== 'shape' && existing.kind !== 'shape';
    if (collisionRelevant && boxesOverlap(normalized, existing)) {
      audit.warnings.push({
        type: 'region_overlap',
        severity: 'error',
        role: normalized.role,
        with: existing.role,
        message: `${normalized.role} overlaps ${existing.role}.`,
      });
    }
  }
  audit.regions.push(normalized);
}

function safeAddText(slide, audit, text, opts) {
  slide.addText(text, opts);
  auditRegion(audit, {
    kind: 'text',
    role: opts.role,
    text,
    fontSize: opts.fontSize,
    bold: opts.bold,
    fit: opts.fit,
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: opts.h,
    protected: opts.protected,
  });
}

function safeAddImage(slide, audit, imageOpts) {
  slide.addImage(imageOpts);
  auditRegion(audit, {
    kind: 'image',
    role: imageOpts.role || 'image',
    x: imageOpts.x,
    y: imageOpts.y,
    w: imageOpts.w,
    h: imageOpts.h,
    protected: imageOpts.protected,
  });
}

function safeAddShape(slide, audit, shapeType, opts) {
  slide.addShape(shapeType, opts);
  auditRegion(audit, {
    kind: 'shape',
    role: opts.role,
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: opts.h,
    protected: false,
  });
}

function slideType(slideData) {
  const raw = String(slideData.type || '').toLowerCase();
  if (raw === 'cover') return 'title';
  if (raw === 'comparison') return 'two_column';
  if (raw === 'visual') return 'image';
  if (raw === 'chart' || raw === 'table' || raw === 'diagram' || raw === 'process') return 'content';
  return raw || 'content';
}

function addBg(slide, template) {
  slide.background = { color: template.background };
}

function addDecorativeSystem(slide, template, variant = 'content') {
  const dark = isDarkTemplate(template);
  const wash = dark ? mixColor(template.surface, template.accent, 0.12) : mixColor(template.background, template.accent, 0.05);
  slide.addShape(currentPptx.ShapeType.rect, {
    x: 0, y: 0, w: 10, h: 5.625,
    fill: { color: template.background },
    line: { color: template.background },
  });
  
  // Premium bleed accent line
  slide.addShape(currentPptx.ShapeType.rect, {
    x: 0, y: 0, w: 10, h: variant === 'title' ? 0.22 : 0.08,
    fill: { color: template.accent },
    line: { color: template.accent },
  });

  // Sleek geometric accents
  slide.addShape(currentPptx.ShapeType.rtTriangle, {
    x: 8.8, y: 0, w: 1.2, h: 1.2,
    fill: { color: template.accent2, transparency: dark ? 65 : 75 },
    line: null,
    flipH: true,
    flipV: true
  });

  if (variant === 'title') {
    slide.addShape(currentPptx.ShapeType.arc, {
      x: 7.2, y: -1.2, w: 4.5, h: 4.5,
      line: { color: template.accent, transparency: dark ? 35 : 45, width: 2.5 },
    });
    slide.addShape(currentPptx.ShapeType.ellipse, {
      x: -0.8, y: 4.2, w: 2.5, h: 2.5,
      line: { color: template.accent2, transparency: dark ? 55 : 65, width: 1.2 },
    });
  } else {
    slide.addShape(currentPptx.ShapeType.rect, {
      x: 0, y: 0.08, w: 0.06, h: 5.545,
      fill: { color: wash, transparency: dark ? 10 : 0 },
      line: null,
    });
  }
}

function addFooter(slide, template, slideNumber, totalSlides, topic) {
  slide.addShape(currentPptx.ShapeType.line, {
    x: 0.48, y: 5.06, w: 9.04, h: 0,
    line: { color: template.ink, transparency: 82, width: 0.6 },
  });
  slide.addText(normalizeText(topic).slice(0, 64), {
    x: 0.52, y: 5.12, w: 6.8, h: 0.18,
    fontFace: template.fontFace, fontSize: 6.6, color: template.muted,
    margin: 0,
  });
  slide.addText(`${slideNumber}/${totalSlides}`, {
    x: 8.82, y: 5.12, w: 0.7, h: 0.18,
    fontFace: template.fontFace, fontSize: 6.6, color: template.muted,
    align: 'right', margin: 0,
  });
}

function addKicker(slide, text, template) {
  if (!text) return;
  slide.addShape(currentPptx.ShapeType.rect, {
    x: 0.52, y: 0.36, w: 0.16, h: 0.16,
    fill: { color: template.accent },
    line: { color: template.accent },
  });
  slide.addText(String(text).toUpperCase(), {
    x: 0.76, y: 0.32, w: 3.8, h: 0.25,
    fontFace: template.fontFace, fontSize: 7.4, bold: true,
    color: template.muted, charSpace: 0.6, margin: 0,
  });
}

function addTitle(slide, title, template, opts = {}) {
  slide.addText(normalizeText(title, 'Untitled slide'), {
    x: opts.x ?? 0.54, y: opts.y ?? 0.62, w: opts.w ?? 8.7, h: opts.h ?? 0.86,
    fontFace: template.headingFace, fontSize: opts.size ?? 28,
    bold: true, color: template.ink, margin: 0.02,
    breakLine: false, fit: 'shrink', charSpace: -0.5,
  });
}

function addSectionLabel(slide, text, template, opts = {}) {
  addKicker(slide, text, template);
  slide.addShape(currentPptx.ShapeType.line, {
    x: opts.x ?? 0.54, y: opts.y ?? 0.62, w: opts.w ?? 1.36, h: 0,
    line: { color: template.accent2, transparency: 18, width: 1.2 },
  });
}

function addSubtitle(slide, text, template, opts = {}) {
  if (!text) return;
  slide.addText(normalizeText(text), {
    x: opts.x ?? 0.54, y: opts.y ?? 1.54, w: opts.w ?? 8.2, h: opts.h ?? 0.42,
    fontFace: template.fontFace, fontSize: opts.size ?? 10.5,
    color: template.muted, margin: 0.02, breakLine: false, fit: 'shrink',
  });
}

function addBullets(slide, bullets, template, opts = {}) {
  const items = cleanBullets(bullets).slice(0, opts.maxItems || 7);
  if (!items.length) return;
  const rich = [];
  items.forEach((item, index) => {
    rich.push({
      text: item,
      options: {
        bullet: { indent: 12 },
        breakLine: index < items.length - 1,
      },
    });
  });
  slide.addText(rich, {
    x: opts.x ?? 0.74, y: opts.y ?? 1.52, w: opts.w ?? 8.2, h: opts.h ?? 3.2,
    fontFace: template.fontFace, fontSize: opts.size ?? 14,
    color: template.ink, fit: 'shrink',
    paraSpaceAfterPt: 8,
    margin: 0.04,
    breakLine: false,
  });
}

function addTextList(slide, bullets, template, opts = {}) {
  const items = cleanBullets(bullets).slice(0, opts.maxItems || 5);
  if (!items.length) return false;
  items.forEach((item, i) => {
    const y = (opts.y ?? 1.5) + i * (opts.rowH ?? 0.42);
    slide.addShape(currentPptx.ShapeType.ellipse, {
      x: opts.x ?? 0.72, y: y + 0.06, w: 0.11, h: 0.11,
      fill: { color: i % 3 === 0 ? template.accent : (i % 3 === 1 ? template.accent2 : template.accent3) },
      line: { color: i % 3 === 0 ? template.accent : (i % 3 === 1 ? template.accent2 : template.accent3) },
    });
    slide.addText(item, {
      x: (opts.x ?? 0.72) + 0.24, y, w: opts.w ?? 5.4, h: opts.h ?? 0.3,
      fontFace: template.fontFace, fontSize: opts.size ?? 10.4,
      color: template.ink, margin: 0.01, fit: 'shrink',
    });
  });
  return true;
}

function addInsightCards(slide, bullets, template, opts = {}) {
  const items = cleanBullets(bullets).slice(0, opts.maxItems || 3);
  if (!items.length) return false;
  const x = opts.x ?? 0.66;
  const y = opts.y ?? 1.58;
  const w = opts.w ?? 6.18;
  const cardH = opts.cardH ?? 0.74;
  const gap = opts.gap ?? 0.18;
  items.forEach((item, i) => {
    const cardY = y + i * (cardH + gap);
    const accent = i % 3 === 0 ? template.accent : (i % 3 === 1 ? template.accent2 : template.accent3);
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x, y: cardY, w, h: cardH,
      rectRadius: 0.04,
      fill: { color: template.surface, transparency: isDarkTemplate(template) ? 8 : 0 },
      line: { color: accent, transparency: 58, width: 0.8 },
    });
    slide.addShape(currentPptx.ShapeType.rect, {
      x, y: cardY, w: 0.08, h: cardH,
      fill: { color: accent },
      line: { color: accent },
    });
    slide.addText(String(i + 1).padStart(2, '0'), {
      x: x + 0.22, y: cardY + 0.18, w: 0.42, h: 0.18,
      fontFace: template.headingFace, fontSize: 8.6, bold: true,
      color: accent, margin: 0,
    });
    slide.addText(item, {
      x: x + 0.76, y: cardY + 0.15, w: w - 0.96, h: cardH - 0.22,
      fontFace: template.fontFace, fontSize: 10,
      color: template.ink, margin: 0.02, fit: 'shrink',
    });
  });
  return true;
}

function addAbstractVisual(slide, template, opts = {}) {
  const x = opts.x ?? 7.02;
  const y = opts.y ?? 1.5;
  const w = opts.w ?? 2.28;
  const h = opts.h ?? 2.74;
  const dark = isDarkTemplate(template);
  
  slide.addShape(currentPptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.04,
    fill: { color: dark ? mixColor(template.surface, template.accent, 0.08) : template.surface, transparency: dark ? 4 : 0 },
    line: { color: template.accent, transparency: 65, width: 0.6 },
  });

  // Premium data-art grid
  const cols = 5;
  const rows = 6;
  const stepX = (w - 0.4) / cols;
  const stepY = (h - 0.6) / rows;
  const colors = [template.accent, template.accent2, template.accent3];
  
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      const cx = x + 0.2 + (c * stepX);
      const cy = y + 0.3 + (r * stepY);
      
      // Dots grid
      slide.addShape(currentPptx.ShapeType.ellipse, {
        x: cx - 0.03, y: cy - 0.03, w: 0.06, h: 0.06,
        fill: { color: template.muted, transparency: 75 },
        line: null
      });

      // Occasional colored geometric elements
      if ((r + c) % 4 === 1 && r < rows && c < cols) {
        const shapeColor = colors[(r * c) % colors.length];
        slide.addShape(currentPptx.ShapeType.rect, {
          x: cx + 0.05, y: cy + 0.05, w: stepX - 0.1, h: stepY - 0.1,
          fill: { color: shapeColor, transparency: dark ? 25 : 35 },
          line: { color: shapeColor, transparency: 40, width: 0.8 },
        });
      }
    }
  }

  // Accent bar
  slide.addShape(currentPptx.ShapeType.rect, {
    x: x + 0.15, y: y + h - 0.25, w: w - 0.3, h: 0.06,
    fill: { color: template.accent, transparency: 15 },
    line: null,
  });
}

function addMetricRail(slide, metrics, template, opts = {}) {
  const items = Array.isArray(metrics) ? metrics.slice(0, opts.maxItems || 3) : [];
  if (!items.length) return;
  const x0 = opts.x ?? 0.58;
  const y = opts.y ?? 4.15;
  const gap = 0.16;
  const w = ((opts.w ?? 8.84) - gap * (items.length - 1)) / items.length;
  items.forEach((metric, idx) => {
    const x = x0 + idx * (w + gap);
    
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x, y, w, h: opts.h ?? 0.76,
      rectRadius: 0.04,
      fill: { color: template.surface, transparency: isDarkTemplate(template) ? 8 : 0 },
      line: { color: template.accent, transparency: 52, width: 0.8 },
    });

    slide.addShape(currentPptx.ShapeType.rect, {
      x, y, w: 0.06, h: opts.h ?? 0.76,
      fill: { color: template.accent },
      line: null,
    });

    slide.addText(normalizeText(metric.value || metric.metric || ''), {
      x: x + 0.16, y: y + 0.14, w: w - 0.32, h: 0.26,
      fontFace: template.headingFace, fontSize: 16, bold: true,
      color: template.accent, margin: 0, fit: 'shrink', charSpace: -0.2
    });
    
    slide.addText(normalizeText(metric.label || metric.name || ''), {
      x: x + 0.16, y: y + 0.44, w: w - 0.32, h: 0.2,
      fontFace: template.fontFace, fontSize: 7.2, bold: true,
      color: template.muted, margin: 0, fit: 'shrink',
    });
  });
}

function parseChartData(chart) {
  if (!chart) return null;
  const chartData = chart.data || chart;
  if (!chartData) return null;

  // Case 1: 2D Array (e.g. [["Industry", "2024", "2028"], ["Healthcare", 15, 45]])
  if (Array.isArray(chartData) && chartData.length > 0 && Array.isArray(chartData[0])) {
    const headers = chartData[0];
    const rows = chartData.slice(1);
    if (headers.length < 2 || rows.length === 0) return null;

    const seriesCount = headers.length - 1;
    const labels = rows.map((row) => String(row[0] || ''));
    const seriesList = [];
    for (let col = 1; col <= seriesCount; col += 1) {
      const name = String(headers[col] || `Series ${col}`);
      const values = rows.map((row) => {
        const val = Number(row[col]);
        return isNaN(val) ? 0 : val;
      });
      seriesList.push({ name, labels, values });
    }
    return seriesList;
  }

  // Case 2: Array of objects (e.g. [{ name: "Actual", labels: [...], values: [...] }])
  if (Array.isArray(chartData) && chartData.length > 0 && typeof chartData[0] === 'object') {
    if (chartData[0].labels && chartData[0].values) {
      return chartData.map((s) => ({
        name: String(s.name || s.series || 'Series'),
        labels: Array.isArray(s.labels) ? s.labels.map(String) : [],
        values: Array.isArray(s.values) ? s.values.map(Number).map((v) => isNaN(v) ? 0 : v) : [],
      }));
    }

    // Case 3: Flat array of points (e.g. [{ label: "Healthcare", value: 15 }])
    const labels = chartData.map((item) => String(item.label || item.name || item.category || ''));
    const values = chartData.map((item) => {
      const val = Number(item.value || item.val || 0);
      return isNaN(val) ? 0 : val;
    });
    return [{
      name: String(chart.title || 'Value'),
      labels,
      values,
    }];
  }

  return null;
}

function addNativeChart(slide, chart, template, opts = {}) {
  if (!chart) return false;
  const chartData = parseChartData(chart);
  if (!chartData || chartData.length === 0) return false;

  const x = opts.x ?? 0.78;
  const y = opts.y ?? 1.82;
  const w = opts.w ?? 8.02;
  const h = opts.h ?? 2.8;

  const chartType = String(chart.chart_type || chart.type || 'bar').toLowerCase();
  let pptxChartType = currentPptx.ChartType.bar;
  if (chartType === 'line') pptxChartType = currentPptx.ChartType.line;
  else if (chartType === 'pie') pptxChartType = currentPptx.ChartType.pie;
  else if (chartType === 'doughnut') pptxChartType = currentPptx.ChartType.doughnut;
  else if (chartType === 'area') pptxChartType = currentPptx.ChartType.area;

  const colors = [template.accent, template.accent2, template.accent3];

  try {
    slide.addChart(pptxChartType, chartData, {
      x, y, w, h,
      title: chart.title || chart.name || '',
      showTitle: !!(chart.title || chart.name),
      titleColor: template.ink,
      titleFontFace: template.headingFace,
      titleFontSize: 11,
      chartColors: colors,
      showLegend: chartData.length > 1 || chartType === 'pie' || chartType === 'doughnut',
      legendColor: template.muted,
      legendFontFace: template.fontFace,
      legendFontSize: 8,
      catAxisLabelColor: template.muted,
      catAxisLabelFontFace: template.fontFace,
      catAxisLabelFontSize: 8,
      valAxisLabelColor: template.muted,
      valAxisLabelFontFace: template.fontFace,
      valAxisLabelFontSize: 8,
      barDir: chartType === 'bar' ? 'bar' : 'col',
    });
    return true;
  } catch (err) {
    console.error('Error adding native chart:', err);
    return false;
  }
}

function addDiagram(slide, nodes, template, opts = {}) {
  const items = Array.isArray(nodes) ? nodes.slice(0, 5) : [];
  if (!items.length) return false;
  const x = opts.x ?? 0.68;
  const y = opts.y ?? 2.05;
  const totalW = opts.w ?? 8.56;
  const gap = 0.16;
  const boxW = (totalW - gap * (items.length - 1)) / items.length;
  items.forEach((node, i) => {
    const boxX = x + i * (boxW + gap);
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x: boxX, y, w: boxW, h: 1.12,
      rectRadius: 0.06,
      fill: { color: template.surface, transparency: template.background === '101828' ? 88 : 0 },
      line: { color: i % 2 ? template.accent2 : template.accent, transparency: 28, width: 1.0 },
    });
    slide.addText(normalizeText(node.title || node.name || node), {
      x: boxX + 0.12, y: y + 0.16, w: boxW - 0.24, h: 0.28,
      fontFace: template.fontFace, fontSize: 9.2, bold: true,
      color: template.ink, margin: 0.02, fit: 'shrink',
    });
    slide.addText(normalizeText(node.detail || node.description || ''), {
      x: boxX + 0.12, y: y + 0.52, w: boxW - 0.24, h: 0.42,
      fontFace: template.fontFace, fontSize: 6.8,
      color: template.muted, margin: 0.02, fit: 'shrink',
    });
    if (i < items.length - 1) {
      slide.addShape(currentPptx.ShapeType.chevron, {
        x: boxX + boxW + 0.035, y: y + 0.42, w: 0.09, h: 0.22,
        fill: { color: template.muted, transparency: 35 },
        line: null,
      });
    }
  });
  return true;
}

function addTable(slide, rows, template, opts = {}) {
  const tableRows = Array.isArray(rows) ? rows.slice(0, 7) : [];
  if (!tableRows.length) return false;
  const normalized = tableRows.map((row) => Array.isArray(row) ? row : Object.values(row || {}));
  const colCount = Math.max(...normalized.map((row) => row.length), 1);
  const x = opts.x ?? 0.68;
  const y = opts.y ?? 1.8;
  const w = opts.w ?? 8.6;
  const rowH = opts.rowH ?? 0.34;
  const colW = w / colCount;
  normalized.forEach((row, r) => {
    for (let c = 0; c < colCount; c += 1) {
      const isHeader = r === 0;
      slide.addShape(currentPptx.ShapeType.rect, {
        x: x + c * colW, y: y + r * rowH, w: colW, h: rowH,
        fill: { color: isHeader ? template.accent : template.surface, transparency: isHeader ? 0 : (template.background === '101828' ? 88 : 0) },
        line: { color: template.ink, transparency: 82, width: 0.4 },
      });
      slide.addText(normalizeText(row[c] ?? ''), {
        x: x + c * colW + 0.06, y: y + r * rowH + 0.06, w: colW - 0.12, h: rowH - 0.1,
        fontFace: template.fontFace, fontSize: isHeader ? 6.8 : 6.6,
        bold: isHeader, color: isHeader ? 'FFFFFF' : template.ink,
        margin: 0, fit: 'shrink',
      });
    }
  });
  return true;
}

function buildTitleSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template } = ctx;
  addBg(slide, template);
  addDecorativeSystem(slide, template, 'title');
  slide.addShape(currentPptx.ShapeType.roundRect, {
    x: 6.82, y: 0.88, w: 2.64, h: 3.78,
    rectRadius: 0.08,
    fill: { color: template.surface, transparency: isDarkTemplate(template) ? 6 : 0 },
    line: { color: template.accent, transparency: 54, width: 1.0 },
  });
  addAbstractVisual(slide, template, { x: 7.02, y: 1.14, w: 2.22, h: 2.46 });
  slide.addText('AETHERIA', {
    x: 7.1, y: 3.88, w: 1.6, h: 0.18,
    fontFace: template.fontFace, fontSize: 6.2, bold: true,
    color: template.muted, charSpace: 1.2, margin: 0,
  });
  addSectionLabel(slide, slideData.kicker || 'Presentation', template);
  addTitle(slide, slideData.title || ctx.topic, template, { x: 0.58, y: 1.12, w: 5.92, h: 1.86, size: 33 });
  addSubtitle(slide, slideData.subtitle || slideData.content, template, { x: 0.62, y: 3.12, w: 5.42, h: 0.62, size: 12 });
  const titleMetrics = Array.isArray(slideData.metrics) && slideData.metrics.length
    ? slideData.metrics
    : cleanBullets(slideData.bullets || slideData.points).slice(0, 3).map((item, i) => ({
      value: `0${i + 1}`,
      label: item,
    }));
  addMetricRail(slide, titleMetrics, template, { x: 0.62, y: 4.18, w: 5.92, maxItems: 3 });
  return slide;
}

function buildContentSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, index, totalSlides, topic } = ctx;
  addBg(slide, template);
  addDecorativeSystem(slide, template, 'content');
  addSectionLabel(slide, slideData.kicker || slideData.section || (slideData.chart ? 'Evidence' : slideData.table ? 'Data' : (slideData.nodes || slideData.steps) ? 'Process' : 'Insight'), template);
  addTitle(slide, slideData.title, template);

  const hasMetrics = Array.isArray(slideData.metrics) && slideData.metrics.length > 0;
  const chartDone = addNativeChart(slide, slideData.chart, template, { x: 0.78, y: 1.82, w: 8.02, h: hasMetrics ? 2.2 : 2.8 });
  const tableDone = !chartDone && addTable(slide, slideData.table, template, { x: 0.76, y: 1.76, w: 8.26, rowH: hasMetrics ? 0.32 : 0.38 });
  const diagramDone = !chartDone && !tableDone && addDiagram(slide, slideData.nodes || slideData.steps, template, { x: 0.78, y: 2.02, w: 8.22 });

  if (!chartDone && !tableDone && !diagramDone) {
    const sourceItems = slideData.bullets || slideData.content || slideData.points;
    const cardH = hasMetrics ? 0.52 : 0.62;
    const gap = hasMetrics ? 0.1 : 0.14;
    const yStart = hasMetrics ? 1.48 : 1.68;
    const visualH = hasMetrics ? 2.10 : 2.46;
    const calloutY = hasMetrics ? 3.68 : 4.10;
    const calloutH = hasMetrics ? 0.3 : 0.36;

    const cardsDone = addInsightCards(slide, sourceItems, template, { x: 0.68, y: yStart, w: 6.06, maxItems: hasMetrics ? 3 : 4, cardH, gap });
    if (!cardsDone) {
      addTextList(slide, sourceItems, template, { x: 0.78, y: yStart, w: 5.8, maxItems: hasMetrics ? 4 : 5 });
    }
    addAbstractVisual(slide, template, { x: 7.06, y: yStart, w: 2.2, h: visualH });
    slide.addText(normalizeText(slideData.callout || slideData.summary || cleanBullets(sourceItems)[0] || 'Key idea'), {
      x: 7.18, y: calloutY, w: 1.96, h: calloutH,
      fontFace: template.headingFace, fontSize: hasMetrics ? 9.5 : 10.5, bold: true,
      color: template.accent, margin: 0.01, fit: 'shrink',
      align: 'center',
    });
  }
  if (hasMetrics) {
    addMetricRail(slide, slideData.metrics, template, { x: 0.66, y: 4.18, w: 8.65, maxItems: 4, h: 0.54 });
  }
  addFooter(slide, template, index, totalSlides, topic);
  return slide;
}

function buildTwoColumnSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, index, totalSlides, topic } = ctx;
  addBg(slide, template);
  addDecorativeSystem(slide, template, 'content');
  addSectionLabel(slide, slideData.kicker || 'Comparison', template);
  addTitle(slide, slideData.title, template);

  const leftTitle = slideData.left_title || slideData.left?.title || 'Current state';
  const rightTitle = slideData.right_title || slideData.right?.title || 'Target state';
  const fallbackItems = cleanBullets(slideData.bullets || slideData.content || slideData.points);
  const midpoint = Math.ceil(fallbackItems.length / 2);
  const leftContent = slideData.left_content || slideData.left_bullets || slideData.left?.content || slideData.left?.bullets || fallbackItems.slice(0, midpoint);
  const rightContent = slideData.right_content || slideData.right_bullets || slideData.right?.content || slideData.right?.bullets || fallbackItems.slice(midpoint);
  [
    { x: 0.66, title: leftTitle, content: leftContent, color: template.accent },
    { x: 5.08, title: rightTitle, content: rightContent, color: template.accent2 },
  ].forEach((col) => {
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x: col.x, y: 1.64, w: 4.08, h: 2.94,
      rectRadius: 0.06,
      fill: { color: template.surface, transparency: template.background === '101828' ? 88 : 0 },
      line: { color: col.color, transparency: 45, width: 1 },
    });
    slide.addShape(currentPptx.ShapeType.rect, {
      x: col.x, y: 1.64, w: 4.08, h: 0.12,
      fill: { color: col.color },
      line: { color: col.color },
    });
    slide.addText(col.title, {
      x: col.x + 0.24, y: 1.9, w: 3.58, h: 0.28,
      fontFace: template.fontFace, fontSize: 10.6, bold: true,
      color: col.color, margin: 0, fit: 'shrink',
    });
    if (!addTextList(slide, col.content, template, {
      x: col.x + 0.28, y: 2.34, w: 3.34, rowH: 0.36, size: 8.8, maxItems: 5,
    })) {
      slide.addText('No comparison details provided', {
        x: col.x + 0.32, y: 2.42, w: 3.28, h: 0.3,
        fontFace: template.fontFace, fontSize: 8.4, italic: true,
        color: template.muted, margin: 0,
      });
    }
  });
  addFooter(slide, template, index, totalSlides, topic);
  return slide;
}

function buildImageSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, index, totalSlides, topic } = ctx;
  addBg(slide, template);
  addDecorativeSystem(slide, template, 'content');
  addSectionLabel(slide, slideData.kicker || 'Visual', template);
  addTitle(slide, slideData.title, template);
  addSubtitle(slide, slideData.caption || slideData.content, template, { x: 0.76, y: 4.44, w: 8.5, size: 8.8 });
  const imagePath = slideData.image_path || slideData.imagePath;
  if (imagePath && fs.existsSync(imagePath)) {
    slide.addImage({ path: imagePath, x: 0.78, y: 1.62, w: 8.42, h: 2.62, sizingCrop: true });
  } else {
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x: 0.78, y: 1.62, w: 8.42, h: 2.62,
      rectRadius: 0.05,
      fill: { color: template.surface, transparency: template.background === '101828' ? 88 : 0 },
      line: { color: template.accent, transparency: 45, width: 1 },
    });
    addAbstractVisual(slide, template, { x: 1.18, y: 1.9, w: 2.3, h: 1.86 });
    addInsightCards(slide, slideData.bullets || slideData.points || slideData.content, template, { x: 3.78, y: 1.92, w: 5.08, maxItems: 3, cardH: 0.48, gap: 0.12 });
    slide.addText(normalizeText(slideData.visual_summary || slideData.summary || 'Visual focus'), {
      x: 1.08, y: 3.88, w: 7.76, h: 0.28,
      fontFace: template.headingFace, fontSize: 13,
      color: template.accent, bold: true, align: 'center',
      margin: 0.01, fit: 'shrink',
    });
  }
  addFooter(slide, template, index, totalSlides, topic);
  return slide;
}

function addVentureBackdrop(slide, template, audit, variant = 'content') {
  safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
    role: 'background',
    x: 0, y: 0, w: SLIDE_W, h: SLIDE_H,
    fill: { color: template.background },
    line: { color: template.background },
  });
  safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
    role: 'left brand rail',
    x: 0, y: 0, w: variant === 'title' ? 0.24 : 0.16, h: SLIDE_H,
    fill: { color: template.accent },
    line: null,
  });
  safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
    role: 'top editorial rule',
    x: 0.54, y: 0.42, w: 1.25, h: 0.035,
    fill: { color: template.accent2 },
    line: null,
  });
  safeAddText(slide, audit, 'AETHERIA / VENTURE BLUEPRINT', {
    role: 'brand label',
    x: 0.56, y: 0.22, w: 2.8, h: 0.14,
    fontFace: template.fontFace, fontSize: 5.9, bold: true,
    color: template.muted, charSpace: 1.1, margin: 0,
    protected: false,
  });
}

function addVentureMetricChips(slide, metrics, template, audit, opts = {}) {
  const items = Array.isArray(metrics) && metrics.length
    ? metrics.slice(0, opts.maxItems || 3)
    : [];
  if (!items.length) return;
  const x0 = opts.x ?? 0.58;
  const y = opts.y ?? 4.36;
  const gap = opts.gap ?? 0.14;
  const totalW = opts.w ?? 4.92;
  const w = (totalW - gap * (items.length - 1)) / items.length;
  items.forEach((metric, i) => {
    const x = x0 + i * (w + gap);
    const accent = i === 1 ? template.accent2 : (i === 2 ? template.accent3 : template.accent);
    safeAddShape(slide, audit, currentPptx.ShapeType.roundRect, {
      role: `metric ${i + 1} chip`,
      x, y, w, h: 0.62,
      rectRadius: 0.045,
      fill: { color: template.surface },
      line: { color: accent, transparency: 28, width: 0.8 },
    });
    safeAddText(slide, audit, normalizeText(metric.value || metric.metric || `0${i + 1}`), {
      role: `metric ${i + 1} value`,
      x: x + 0.14, y: y + 0.12, w: w - 0.28, h: 0.21,
      fontFace: template.headingFace, fontSize: 13.2, bold: true,
      color: accent, margin: 0, fit: 'shrink',
    });
    safeAddText(slide, audit, normalizeText(metric.label || metric.name || ''), {
      role: `metric ${i + 1} label`,
      x: x + 0.14, y: y + 0.38, w: w - 0.28, h: 0.14,
      fontFace: template.fontFace, fontSize: 5.9, bold: true,
      color: template.muted, margin: 0, fit: 'shrink',
    });
  });
}

function addVentureVisualPanel(slide, slideData, template, audit, opts = {}) {
  const x = opts.x ?? 6.05;
  const y = opts.y ?? 0.66;
  const w = opts.w ?? 3.34;
  const h = opts.h ?? 4.26;
  const imagePath = slideData.image_path || slideData.imagePath;
  safeAddShape(slide, audit, currentPptx.ShapeType.roundRect, {
    role: 'visual panel frame',
    x, y, w, h,
    rectRadius: 0.08,
    fill: { color: template.surface },
    line: { color: template.accent, transparency: 24, width: 1 },
  });
  if (imagePath && fs.existsSync(imagePath)) {
    safeAddImage(slide, audit, {
      role: 'main visual image',
      path: imagePath,
      x: x + 0.12, y: y + 0.12, w: w - 0.24, h: h - 0.86,
      sizingCrop: true,
    });
  } else {
    safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
      role: 'abstract market block',
      x: x + 0.24, y: y + 0.28, w: w - 0.48, h: 1.05,
      fill: { color: mixColor(template.accent, template.surface, 0.12), transparency: 8 },
      line: null,
    });
    safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
      role: 'abstract product block',
      x: x + 0.24, y: y + 1.52, w: w - 0.92, h: 0.82,
      fill: { color: template.accent2, transparency: 12 },
      line: null,
    });
    safeAddShape(slide, audit, currentPptx.ShapeType.rect, {
      role: 'abstract growth block',
      x: x + 0.84, y: y + 2.54, w: w - 1.08, h: 0.72,
      fill: { color: template.accent3, transparency: 18 },
      line: null,
    });
  }
  safeAddText(slide, audit, normalizeText(slideData.visual_summary || slideData.summary || 'Designed for sharp business storytelling'), {
    role: 'visual panel caption',
    x: x + 0.26, y: y + h - 0.54, w: w - 0.52, h: 0.24,
    fontFace: template.fontFace, fontSize: 7.8, bold: true,
    color: template.accent, align: 'center', margin: 0.01, fit: 'shrink',
  });
}

function addVentureFooter(slide, template, audit, ctx) {
  safeAddShape(slide, audit, currentPptx.ShapeType.line, {
    role: 'footer rule',
    x: 0.54, y: 5.18, w: 8.9, h: 0,
    line: { color: template.ink, transparency: 84, width: 0.5 },
  });
  safeAddText(slide, audit, normalizeText(ctx.topic).slice(0, 72), {
    role: 'footer topic',
    x: 0.58, y: 5.25, w: 6.9, h: 0.12,
    fontFace: template.fontFace, fontSize: 5.6, color: template.muted, margin: 0,
    protected: false,
  });
  safeAddText(slide, audit, `${ctx.index}/${ctx.totalSlides}`, {
    role: 'footer page number',
    x: 8.94, y: 5.25, w: 0.46, h: 0.12,
    fontFace: template.fontFace, fontSize: 5.6, color: template.muted, align: 'right', margin: 0,
    protected: false,
  });
}

function buildVentureTitleSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, audit } = ctx;
  addVentureBackdrop(slide, template, audit, 'title');
  addVentureVisualPanel(slide, slideData, template, audit, { x: 6.05, y: 0.7, w: 3.32, h: 4.16 });
  safeAddText(slide, audit, normalizeText(slideData.kicker || 'Pitch narrative'), {
    role: 'cover kicker',
    x: 0.58, y: 0.78, w: 2.25, h: 0.18,
    fontFace: template.fontFace, fontSize: 7.2, bold: true,
    color: template.accent2, charSpace: 0.8, margin: 0, fit: 'shrink',
  });
  safeAddText(slide, audit, normalizeText(slideData.title || ctx.topic), {
    role: 'cover headline',
    x: 0.56, y: 1.14, w: 4.92, h: 1.7,
    fontFace: template.headingFace, fontSize: 31, bold: true,
    color: template.ink, margin: 0.02, fit: 'shrink',
  });
  safeAddText(slide, audit, normalizeText(slideData.subtitle || slideData.content || 'A concise, investor-ready business story built around traction, evidence, and execution.'), {
    role: 'cover subtitle',
    x: 0.6, y: 3.12, w: 4.54, h: 0.46,
    fontFace: template.fontFace, fontSize: 10.4,
    color: template.muted, margin: 0.02, fit: 'shrink',
  });
  const fallbackMetrics = cleanBullets(slideData.bullets || slideData.points).slice(0, 3).map((item, i) => ({ value: `0${i + 1}`, label: item }));
  addVentureMetricChips(slide, slideData.metrics || fallbackMetrics, template, audit, { x: 0.58, y: 4.16, w: 4.9 });
  return slide;
}

function buildVentureContentSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, audit } = ctx;
  addVentureBackdrop(slide, template, audit, 'content');
  safeAddText(slide, audit, normalizeText(slideData.kicker || slideData.section || 'Strategic insight'), {
    role: 'section kicker',
    x: 0.58, y: 0.7, w: 2.2, h: 0.16,
    fontFace: template.fontFace, fontSize: 6.8, bold: true,
    color: template.accent2, charSpace: 0.6, margin: 0, fit: 'shrink',
  });
  safeAddText(slide, audit, normalizeText(slideData.title), {
    role: 'left thesis headline',
    x: 0.56, y: 0.98, w: 3.24, h: 1.45,
    fontFace: template.headingFace, fontSize: 23,
    bold: true, color: template.ink, margin: 0.02, fit: 'shrink',
  });
  safeAddText(slide, audit, normalizeText(slideData.callout || slideData.summary || 'The key idea should be visible at a glance.'), {
    role: 'left callout',
    x: 0.62, y: 2.68, w: 2.84, h: 0.58,
    fontFace: template.fontFace, fontSize: 10, bold: true,
    color: template.accent, margin: 0.02, fit: 'shrink',
  });

  const hasChart = addNativeChart(slide, slideData.chart, template, { x: 4.1, y: 1.04, w: 4.92, h: 2.75 });
  if (hasChart) {
    auditRegion(audit, { kind: 'image', role: 'chart canvas', x: 4.1, y: 1.04, w: 4.92, h: 2.75 });
  } else if (addTable(slide, slideData.table, template, { x: 4.06, y: 1.06, w: 5.08, rowH: 0.34 })) {
    auditRegion(audit, { kind: 'image', role: 'table canvas', x: 4.06, y: 1.06, w: 5.08, h: 2.72 });
  } else if (addDiagram(slide, slideData.nodes || slideData.steps, template, { x: 4.04, y: 1.52, w: 5.16 })) {
    auditRegion(audit, { kind: 'image', role: 'roadmap diagram', x: 4.04, y: 1.52, w: 5.16, h: 1.18 });
  } else {
    const items = cleanBullets(slideData.bullets || slideData.content || slideData.points).slice(0, 4);
    items.forEach((item, i) => {
      const y = 1.04 + i * 0.82;
      const accent = i === 1 ? template.accent2 : (i === 2 ? template.accent3 : template.accent);
      safeAddShape(slide, audit, currentPptx.ShapeType.roundRect, {
        role: `proof card ${i + 1}`,
        x: 4.08, y, w: 4.92, h: 0.62,
        rectRadius: 0.045,
        fill: { color: template.surface },
        line: { color: accent, transparency: 44, width: 0.7 },
      });
      safeAddText(slide, audit, String(i + 1).padStart(2, '0'), {
        role: `proof card ${i + 1} number`,
        x: 4.3, y: y + 0.18, w: 0.34, h: 0.16,
        fontFace: template.headingFace, fontSize: 8.2, bold: true,
        color: accent, margin: 0,
      });
      safeAddText(slide, audit, item, {
        role: `proof card ${i + 1} text`,
        x: 4.72, y: y + 0.13, w: 4.02, h: 0.34,
        fontFace: template.fontFace, fontSize: 8.2,
        color: template.ink, margin: 0.01, fit: 'shrink',
      });
    });
  }
  if (Array.isArray(slideData.metrics) && slideData.metrics.length) {
    addVentureMetricChips(slide, slideData.metrics, template, audit, { x: 4.08, y: 4.08, w: 4.96, maxItems: 3 });
  }
  addVentureFooter(slide, template, audit, ctx);
  return slide;
}

function buildVentureTwoColumnSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, audit } = ctx;
  addVentureBackdrop(slide, template, audit, 'content');
  safeAddText(slide, audit, normalizeText(slideData.title), {
    role: 'comparison headline',
    x: 0.56, y: 0.82, w: 8.34, h: 0.62,
    fontFace: template.headingFace, fontSize: 24, bold: true,
    color: template.ink, margin: 0.02, fit: 'shrink',
  });
  const fallbackItems = cleanBullets(slideData.bullets || slideData.content || slideData.points);
  const midpoint = Math.ceil(fallbackItems.length / 2);
  const columns = [
    {
      x: 0.72,
      w: 3.92,
      color: template.accent2,
      title: slideData.left_title || slideData.left?.title || 'Problem',
      content: slideData.left_content || slideData.left_bullets || slideData.left?.content || slideData.left?.bullets || fallbackItems.slice(0, midpoint),
    },
    {
      x: 5.08,
      w: 3.92,
      color: template.accent3,
      title: slideData.right_title || slideData.right?.title || 'Solution',
      content: slideData.right_content || slideData.right_bullets || slideData.right?.content || slideData.right?.bullets || fallbackItems.slice(midpoint),
    },
  ];
  columns.forEach((col, colIndex) => {
    safeAddShape(slide, audit, currentPptx.ShapeType.roundRect, {
      role: `${col.title} panel`,
      x: col.x, y: 1.74, w: col.w, h: 2.84,
      rectRadius: 0.06,
      fill: { color: template.surface },
      line: { color: col.color, transparency: 25, width: 1 },
    });
    safeAddText(slide, audit, normalizeText(col.title), {
      role: `${col.title} panel title`,
      x: col.x + 0.26, y: 2.02, w: col.w - 0.52, h: 0.25,
      fontFace: template.headingFace, fontSize: 14,
      bold: true, color: col.color, margin: 0, fit: 'shrink',
    });
    cleanBullets(col.content).slice(0, 4).forEach((item, i) => {
      const y = 2.52 + i * 0.42;
      safeAddShape(slide, audit, currentPptx.ShapeType.ellipse, {
        role: `${col.title} bullet ${i + 1} marker`,
        x: col.x + 0.3, y: y + 0.07, w: 0.08, h: 0.08,
        fill: { color: col.color },
        line: null,
      });
      safeAddText(slide, audit, item, {
        role: `${col.title} bullet ${i + 1}`,
        x: col.x + 0.5, y, w: col.w - 0.86, h: 0.22,
        fontFace: template.fontFace, fontSize: 8.6,
        color: template.ink, margin: 0.01, fit: 'shrink',
      });
    });
    safeAddText(slide, audit, colIndex === 0 ? '01' : '02', {
      role: `${col.title} panel index`,
      x: col.x + col.w - 0.72, y: 4.18, w: 0.42, h: 0.16,
      fontFace: template.headingFace, fontSize: 7.8,
      bold: true, color: col.color, margin: 0, protected: false,
    });
  });
  addVentureFooter(slide, template, audit, ctx);
  return slide;
}

function buildVentureImageSlide(pptx, slideData, ctx) {
  const slide = pptx.addSlide();
  const { template, audit } = ctx;
  addVentureBackdrop(slide, template, audit, 'content');
  safeAddText(slide, audit, normalizeText(slideData.kicker || 'Product / vision'), {
    role: 'visual kicker',
    x: 0.58, y: 0.72, w: 2.2, h: 0.16,
    fontFace: template.fontFace, fontSize: 6.8, bold: true,
    color: template.accent2, charSpace: 0.6, margin: 0, fit: 'shrink',
  });
  safeAddText(slide, audit, normalizeText(slideData.title), {
    role: 'visual headline',
    x: 0.56, y: 1.02, w: 3.12, h: 1.18,
    fontFace: template.headingFace, fontSize: 22,
    bold: true, color: template.ink, margin: 0.02, fit: 'shrink',
  });
  const bullets = cleanBullets(slideData.bullets || slideData.points || slideData.content).slice(0, 3);
  bullets.forEach((item, i) => {
    safeAddText(slide, audit, item, {
      role: `visual support point ${i + 1}`,
      x: 0.66, y: 2.58 + i * 0.44, w: 2.84, h: 0.2,
      fontFace: template.fontFace, fontSize: 8.2,
      color: template.muted, margin: 0.01, fit: 'shrink',
    });
  });
  addVentureVisualPanel(slide, slideData, template, audit, { x: 4.08, y: 0.86, w: 5.12, h: 3.82 });
  addVentureFooter(slide, template, audit, ctx);
  return slide;
}

function normalizeSlide(slide, index, topic) {
  if (!slide || typeof slide !== 'object') {
    return { type: 'content', title: `Slide ${index + 1}`, bullets: [normalizeText(slide)] };
  }
  const normalized = { ...slide };
  normalized.type = String(slide.type || (index === 0 ? 'title' : 'content')).toLowerCase();
  normalized.title = normalizeText(slide.title || (index === 0 ? topic : `Slide ${index + 1}`));
  if ((normalized.type === 'chart' || normalized.type === 'evidence') && !normalized.chart) {
    normalized.chart = normalized.data ? { title: normalized.chart_title || normalized.title, data: normalized.data } : normalized.chart;
  }
  if ((normalized.type === 'diagram' || normalized.type === 'process') && !(normalized.nodes || normalized.steps)) {
    normalized.nodes = cleanBullets(normalized.bullets || normalized.content || normalized.points).slice(0, 5).map((item) => ({ title: item }));
  }
  return normalized;
}

function buildPresentation(payload) {
  const pptx = new PptxGenJS();
  currentPptx = pptx;
  pptx.author = 'Aetheria ai';
  pptx.company = 'Aetheria ai';
  pptx.subject = normalizeText(payload.topic || 'AI generated presentation');
  pptx.title = normalizeText(payload.topic || 'Presentation');
  pptx.lang = 'en-US';
  pptx.layout = 'LAYOUT_WIDE';
  pptx.theme = {
    headFontFace: 'Aptos Display',
    bodyFontFace: 'Aptos',
    lang: 'en-US',
  };

  const template = pickTemplate(payload.template);
  const topic = normalizeText(payload.topic || 'Presentation');
  const rawSlides = Array.isArray(payload.slides) && payload.slides.length
    ? payload.slides
    : [{ type: 'title', title: topic }, { type: 'content', title: 'Key points', bullets: cleanBullets(payload.content || '') }];
  const slides = rawSlides.map((slide, index) => normalizeSlide(slide, index, topic));
  const layoutAudits = [];

  slides.forEach((slideData, idx) => {
    const audit = createLayoutAudit(idx + 1, slideData);
    const ctx = { template, topic, index: idx + 1, totalSlides: slides.length, audit };
    let slide;
    const kind = slideType(slideData);
    if (payload.template === 'venture_blueprint' && kind === 'title') {
      slide = buildVentureTitleSlide(pptx, slideData, ctx);
    } else if (payload.template === 'venture_blueprint' && kind === 'two_column') {
      slide = buildVentureTwoColumnSlide(pptx, slideData, ctx);
    } else if (payload.template === 'venture_blueprint' && kind === 'image') {
      slide = buildVentureImageSlide(pptx, slideData, ctx);
    } else if (payload.template === 'venture_blueprint') {
      slide = buildVentureContentSlide(pptx, slideData, ctx);
    } else if (kind === 'title') {
      slide = buildTitleSlide(pptx, slideData, ctx);
    } else if (kind === 'two_column') {
      slide = buildTwoColumnSlide(pptx, slideData, ctx);
    } else if (kind === 'image') {
      slide = buildImageSlide(pptx, slideData, ctx);
    } else {
      slide = buildContentSlide(pptx, slideData, ctx);
    }
    if (slideData.notes) {
      slide.addNotes(normalizeText(slideData.notes));
    }
    if (payload.template === 'venture_blueprint') {
      layoutAudits.push({
        slide_index: audit.slide_index,
        title: audit.title,
        region_count: audit.regions.length,
        warnings: audit.warnings,
      });
    }
  });

  return { pptx, slides, template, layoutAudits };
}

async function main() {
  const payloadPath = process.argv[2];
  if (!payloadPath) {
    throw new Error('Usage: node pptx-renderer.js <payload.json>');
  }
  const payload = readJson(payloadPath);
  if (!payload.output_path) {
    throw new Error('payload.output_path is required');
  }
  fs.mkdirSync(path.dirname(payload.output_path), { recursive: true });

  const { pptx, slides, template, layoutAudits } = buildPresentation(payload);
  await pptx.writeFile({ fileName: payload.output_path });
  const stat = fs.statSync(payload.output_path);
  writeJson({
    ok: true,
    output_path: payload.output_path,
    mime_type: PPTX_MIME,
    size: stat.size,
    template: {
      id: payload.template || 'aetheria_modern',
      name: template.name,
      description: template.description,
      colors: {
        background: template.background,
        surface: template.surface,
        ink: template.ink,
        muted: template.muted,
        accent: template.accent,
        accent2: template.accent2,
        accent3: template.accent3,
      },
    },
    layout_validation: {
      ok: !layoutAudits.some((audit) => audit.warnings.some((warning) => warning.severity === 'error')),
      warning_count: layoutAudits.reduce((count, audit) => count + audit.warnings.length, 0),
      audits: layoutAudits,
    },
    slides: slides.map((slide, index) => ({
      index: index + 1,
      type: slide.type,
      layout: slideType(slide),
      title: slide.title,
      subtitle: normalizeText(slide.subtitle || slide.caption || '').slice(0, 180),
      bullets: cleanBullets(slide.bullets || slide.content || slide.points).slice(0, 4),
      has_chart: Boolean(slide.chart),
      has_table: Boolean(slide.table),
      has_diagram: Boolean(slide.nodes || slide.steps),
      has_visual: slideType(slide) === 'image' || Boolean(slide.image_path || slide.imagePath),
      metrics: Array.isArray(slide.metrics) ? slide.metrics.slice(0, 4) : [],
    })),
  });
}

main().catch((error) => {
  writeJson({ ok: false, error: error.message, stack: error.stack });
  process.exitCode = 1;
});
