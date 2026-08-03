#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

const PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
const CANVAS_W = 1920;
const CANVAS_H = 1080;
const SLIDE_W_IN = 13.333333;
const SLIDE_H_IN = 7.5;
const PX_TO_IN = SLIDE_W_IN / CANVAS_W;
const BODY_FONT = 'Segoe UI';
const HEADING_FONT = 'Segoe UI Semibold';
const SERIF_HEADING_FONT = 'Georgia';

let currentPptx = null;

const BUILT_IN_TEMPLATES = {
  venture_blueprint: {
    name: 'Venture Blueprint',
    description: 'Premium pitch and business deck with bold left-rail titles, editorial image zones, and investor-grade evidence layouts.',
    background: 'F7F4EE',
    surface: 'FFFCF7',
    ink: '173042',
    muted: '637083',
    accent: '143C5A',
    accent2: 'E4572E',
    accent3: '2FBF71',
    grid: 'D9D1C5',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
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
    grid: 'D7DCCF',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
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
    grid: 'E4DFD2',
    fontFace: BODY_FONT,
    headingFace: SERIF_HEADING_FONT,
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
    grid: '23314C',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
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
    grid: 'D8E0EC',
    fontFace: BODY_FONT,
    headingFace: SERIF_HEADING_FONT,
  },
  creative_portfolio: {
    name: 'Creative Portfolio',
    description: 'Bold expressive deck with vibrant asymmetric layouts.',
    background: '1A1025',
    surface: '261438',
    ink: 'F8F0FF',
    muted: 'C4A8E0',
    accent: 'FF6B6B',
    accent2: 'C084FC',
    accent3: '4ADE80',
    grid: '3A2450',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
  },
  minimal_zen: {
    name: 'Minimal Zen',
    description: 'Ultra-clean whitespace design with restrained emphasis.',
    background: 'FAFAFA',
    surface: 'FFFFFF',
    ink: '18181B',
    muted: '71717A',
    accent: '3B82F6',
    accent2: '52525B',
    accent3: '10B981',
    grid: 'E4E4E7',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
  },
  tech_dark: {
    name: 'Tech Neon',
    description: 'Dark engineering theme with electric accents and sharp diagrams.',
    background: '0A0E17',
    surface: '121A28',
    ink: 'E8ECF2',
    muted: '8899AA',
    accent: '00E5FF',
    accent2: 'FF3D71',
    accent3: '00E096',
    grid: '1E2B3F',
    fontFace: BODY_FONT,
    headingFace: HEADING_FONT,
  },
  corporate_gradient: {
    name: 'Corporate Horizon',
    description: 'Professional deck with structured visual hierarchy.',
    background: 'F8FAFC',
    surface: 'FFFFFF',
    ink: '0F172A',
    muted: '5B6578',
    accent: '0F4C81',
    accent2: 'E07A2F',
    accent3: '2E8B57',
    grid: 'D8E1EE',
    fontFace: BODY_FONT,
    headingFace: SERIF_HEADING_FONT,
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
    return value.map((item) => normalizeText(item).replace(/^[\s*-]+/, '').trim()).filter(Boolean);
  }
  return normalizeText(value)
    .split(/\r?\n|;/)
    .map((line) => line.replace(/^[\s*-]+/, '').trim())
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
  const c = safeColor(template.background, 'FFFFFF');
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
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
  return [r, g, b]
    .map((value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
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

function luminance(color) {
  const rgb = hexToRgb(color);
  const channels = [rgb.r, rgb.g, rgb.b].map((value) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(a, b) {
  const l1 = luminance(a);
  const l2 = luminance(b);
  const light = Math.max(l1, l2);
  const dark = Math.min(l1, l2);
  return (light + 0.05) / (dark + 0.05);
}

function readableColor(template, color, background) {
  const bg = background || template.surface || template.background;
  if (contrastRatio(color, bg) >= 4.2) return color;
  return isDarkTemplate(template)
    ? mixColor(color, 'FFFFFF', 0.48)
    : mixColor(color, '000000', 0.32);
}

function px(value) {
  return Math.round(Number(value || 0));
}

function toIn(value) {
  return Number((Number(value || 0) * PX_TO_IN).toFixed(4));
}

function fontPx(pt) {
  return Number(pt || 10) * 96 / 72;
}

function decodeHtml(value) {
  return String(value || '')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function stripTags(value) {
  return decodeHtml(String(value || '').replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function parseAttrs(tag) {
  const attrs = {};
  const attrRegex = /([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;
  let match;
  while ((match = attrRegex.exec(tag))) {
    attrs[match[1].toLowerCase()] = decodeHtml(match[2] ?? match[3] ?? match[4] ?? '');
  }
  return attrs;
}

function parseStyle(styleText) {
  const style = {};
  String(styleText || '').split(';').forEach((rule) => {
    const idx = rule.indexOf(':');
    if (idx <= 0) return;
    const key = rule.slice(0, idx).trim().toLowerCase();
    const value = rule.slice(idx + 1).trim();
    if (key) style[key] = value;
  });
  return style;
}

function cssNumber(value, fallback = 0) {
  const match = String(value || '').match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : fallback;
}

function cssColorToHex(value, fallback) {
  const text = String(value || '').trim();
  const hex = text.match(/^#?([0-9a-f]{6})$/i);
  if (hex) return hex[1].toUpperCase();
  const short = text.match(/^#?([0-9a-f]{3})$/i);
  if (short) return short[1].split('').map((ch) => ch + ch).join('').toUpperCase();
  const rgb = text.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  if (rgb) return rgbToHex({ r: Number(rgb[1]), g: Number(rgb[2]), b: Number(rgb[3]) });
  return fallback;
}

function cssStyleToObject(styleMap, objectType, template) {
  const fontFamily = String(styleMap['font-family'] || '').split(',')[0].replace(/["']/g, '').trim();
  const style = { shape: styleMap['border-radius'] && cssNumber(styleMap['border-radius']) > 0 ? 'roundRect' : 'rect' };
  const fill = cssColorToHex(styleMap.background || styleMap['background-color'] || styleMap.fill, null);
  const color = cssColorToHex(styleMap.color, null);
  const border = String(styleMap.border || '');
  const borderColor = cssColorToHex(styleMap['border-color'], null) || cssColorToHex((border.match(/#[0-9a-f]{3,6}|rgba?\([^)]+\)/i) || [])[0], null);
  if (objectType === 'textbox') {
    style.fontFace = fontFamily || BODY_FONT;
    style.fontSizePt = cssNumber(styleMap['font-size'], 16) * 72 / 96;
    style.lineHeight = cssNumber(styleMap['line-height'], 1.12);
    style.bold = /bold|[6-9]00/.test(String(styleMap['font-weight'] || ''));
    style.italic = String(styleMap['font-style'] || '').includes('italic');
    style.color = color || template.ink;
    style.align = styleMap['text-align'] || 'left';
  } else {
    style.fill = fill || 'FFFFFF';
    style.line = borderColor || fill || template.grid;
    style.lineWidth = cssNumber(styleMap['border-width'] || border, borderColor ? 1 : 0);
  }
  if (fill && objectType === 'textbox') style.fill = fill;
  if (borderColor && objectType === 'textbox') {
    style.line = borderColor;
    style.lineWidth = cssNumber(styleMap['border-width'] || border, 1);
  }
  if (styleMap.opacity != null) style.opacity = Math.max(0, Math.min(1, Number(styleMap.opacity)));
  if (styleMap['border-radius']) style.radius = cssNumber(styleMap['border-radius']);
  return style;
}

function extractSlideContainer(html) {
  const source = String(html || '');
  const open = source.match(/<[^>]*class\s*=\s*["'][^"']*\bslide-container\b[^"']*["'][^>]*>/i);
  if (!open || open.index == null) return source;
  const start = open.index + open[0].length;
  const end = source.toLowerCase().lastIndexOf('</div>');
  return end > start ? source.slice(start, end) : source.slice(start);
}

function parseContractHtml(html, template) {
  const source = extractSlideContainer(html);
  const warnings = [];
  const objects = [];
  const objectRegex = /<(div|img)\b([^>]*data-object\s*=\s*["']true["'][^>]*)>([\s\S]*?)<\/div>|<(img)\b([^>]*data-object\s*=\s*["']true["'][^>]*)\/?>/gi;
  let match;
  while ((match = objectRegex.exec(source))) {
    const tag = (match[1] || match[4] || '').toLowerCase();
    const attrs = parseAttrs(match[2] || match[5] || '');
    const styleMap = parseStyle(attrs.style || '');
    const type = String(attrs['data-object-type'] || (tag === 'img' ? 'image' : 'shape')).toLowerCase();
    const id = attrs['data-object-id'] || attrs.id || `${type}-${objects.length + 1}`;
    const object = {
      id,
      type,
      objectType: type,
      role: attrs['data-role'] || id,
      x: cssNumber(styleMap.left, NaN),
      y: cssNumber(styleMap.top, NaN),
      w: cssNumber(styleMap.width, NaN),
      h: cssNumber(styleMap.height, NaN),
      z: cssNumber(styleMap['z-index'], objects.length + 1),
      text: type === 'textbox' ? stripTags(match[3] || '') : undefined,
      style: cssStyleToObject(styleMap, type, template),
      data: null,
      decorative: attrs['data-decorative'] === 'true',
      protected: attrs['data-protected'] !== 'false',
    };
    if (tag === 'img' || type === 'image') {
      object.type = 'image';
      object.data = { imagePath: attrs.src || '' };
    }
    ['left', 'top', 'width', 'height'].forEach((required) => {
      if (!styleMap[required]) warnings.push({ type: 'contract_missing_style', severity: 'error', object_id: id, message: `${id} is missing inline ${required}.` });
    });
    if (styleMap.position !== 'absolute') warnings.push({ type: 'contract_position', severity: 'error', object_id: id, message: `${id} must use position:absolute.` });
    if (!['textbox', 'shape', 'image', 'chart', 'table', 'diagram', 'icon'].includes(object.type)) warnings.push({ type: 'contract_object_type', severity: 'error', object_id: id, message: `${id} uses unsupported data-object-type '${object.type}'.` });
    objects.push(object);
  }
  if (!objects.length) warnings.push({ type: 'contract_no_objects', severity: 'error', message: 'No direct data-object="true" objects found.' });
  return { objects, warnings };
}
function slideType(slideData) {
  const raw = String(slideData.type || '').toLowerCase();
  if (raw === 'cover') return 'title';
  if (raw === 'comparison') return 'two_column';
  if (raw === 'visual') return 'image';
  if (raw === 'process') return 'diagram';
  return raw || 'content';
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

function createSlideSpec(slideData, index, ctx) {
  return {
    index,
    id: `slide-${index}`,
    type: slideType(slideData),
    title: normalizeText(slideData.title || `Slide ${index}`),
    notes: normalizeText(slideData.notes || ''),
    canvas: { width: CANVAS_W, height: CANVAS_H },
    template: ctx.template,
    objects: [],
  };
}

function addObject(spec, object) {
  const normalized = {
    id: object.id || `${object.type || 'object'}-${spec.objects.length + 1}`,
    type: object.type || 'shape',
    objectType: object.objectType || object.type || 'shape',
    role: object.role || object.id || `${object.type || 'object'} ${spec.objects.length + 1}`,
    x: px(object.x),
    y: px(object.y),
    w: px(object.w),
    h: px(object.h),
    z: Number(object.z || 1),
    text: object.text == null ? undefined : normalizeText(object.text),
    style: object.style || {},
    data: object.data || null,
    decorative: Boolean(object.decorative),
    protected: object.protected !== false,
  };
  spec.objects.push(normalized);
  return normalized;
}

function addBackground(spec, template) {
  addObject(spec, {
    id: 'background',
    type: 'shape',
    role: 'slide background',
    x: 0,
    y: 0,
    w: CANVAS_W,
    h: CANVAS_H,
    z: 0,
    decorative: true,
    protected: false,
    style: { fill: template.background, line: template.background, shape: 'rect' },
  });
  addObject(spec, {
    id: 'brand-rail',
    type: 'shape',
    role: 'brand rail',
    x: 0,
    y: 0,
    w: 48,
    h: CANVAS_H,
    z: 1,
    decorative: true,
    protected: false,
    style: { fill: template.accent, line: template.accent, shape: 'rect' },
  });
  for (let i = 0; i < 9; i += 1) {
    addObject(spec, {
      id: `grid-line-${i}`,
      type: 'shape',
      role: 'layout grid line',
      x: 160 + i * 180,
      y: 0,
      w: 1,
      h: CANVAS_H,
      z: 1,
      decorative: true,
      protected: false,
      style: { fill: template.grid, opacity: isDarkTemplate(template) ? 0.12 : 0.2, shape: 'rect' },
    });
  }
}

function addBrand(spec, template, label = 'AETHERIA / PRESENTATION') {
  addObject(spec, {
    id: 'brand-label',
    type: 'textbox',
    role: 'brand label',
    x: 112,
    y: 58,
    w: 430,
    h: 28,
    z: 4,
    protected: false,
    text: label.toUpperCase(),
    style: { fontFace: template.fontFace, fontSizePt: 8, bold: true, color: template.muted, letterSpacing: 1.2 },
  });
  addObject(spec, {
    id: 'brand-rule',
    type: 'shape',
    role: 'brand rule',
    x: 112,
    y: 95,
    w: 240,
    h: 6,
    z: 4,
    decorative: true,
    protected: false,
    style: { fill: template.accent2, shape: 'rect' },
  });
}

function addFooter(spec, template, index, totalSlides, topic) {
  addObject(spec, {
    id: 'footer-rule',
    type: 'shape',
    role: 'footer rule',
    x: 112,
    y: 1000,
    w: 1690,
    h: 1,
    z: 4,
    decorative: true,
    protected: false,
    style: { fill: mixColor(template.ink, template.background, 0.82), opacity: 0.55, shape: 'rect' },
  });
  addObject(spec, {
    id: 'footer-topic',
    type: 'textbox',
    role: 'footer topic',
    x: 112,
    y: 1018,
    w: 900,
    h: 22,
    z: 5,
    protected: false,
    text: normalizeText(topic).slice(0, 78),
    style: { fontFace: template.fontFace, fontSizePt: 7, color: template.muted },
  });
  addObject(spec, {
    id: 'footer-page',
    type: 'textbox',
    role: 'footer page',
    x: 1690,
    y: 1018,
    w: 110,
    h: 22,
    z: 5,
    protected: false,
    text: `${index}/${totalSlides}`,
    style: { fontFace: template.fontFace, fontSizePt: 7, color: template.muted, align: 'right' },
  });
}

function addMetricChips(spec, metrics, template, opts = {}) {
  const items = Array.isArray(metrics) ? metrics.slice(0, opts.maxItems || 3) : [];
  if (!items.length) return;
  const x0 = opts.x ?? 112;
  const y = opts.y ?? 820;
  const totalW = opts.w ?? 900;
  const gap = opts.gap ?? 28;
  const w = Math.floor((totalW - gap * (items.length - 1)) / items.length);
  items.forEach((metric, idx) => {
    const x = x0 + idx * (w + gap);
    const accent = idx === 1 ? template.accent2 : idx === 2 ? template.accent3 : template.accent;
    addObject(spec, {
      id: `metric-${idx + 1}-card`,
      type: 'shape',
      role: `metric ${idx + 1} card`,
      x,
      y,
      w,
      h: opts.h ?? 104,
      z: 8,
      protected: false,
      style: { fill: template.surface, line: accent, lineWidth: 1.6, radius: 10, shape: 'roundRect' },
    });
    addObject(spec, {
      id: `metric-${idx + 1}-value`,
      type: 'textbox',
      role: `metric ${idx + 1} value`,
      x: x + 28,
      y: y + 24,
      w: w - 56,
      h: 38,
      z: 9,
      text: normalizeText(metric.value || metric.metric || ''),
      style: { fontFace: template.headingFace, fontSizePt: opts.valueSizePt ?? 19, bold: true, color: readableColor(template, accent, template.surface) },
    });
    addObject(spec, {
      id: `metric-${idx + 1}-label`,
      type: 'textbox',
      role: `metric ${idx + 1} label`,
      x: x + 30,
      y: y + 68,
      w: w - 60,
      h: 24,
      z: 9,
      text: normalizeText(metric.label || metric.name || ''),
      style: { fontFace: template.fontFace, fontSizePt: opts.labelSizePt ?? 8, bold: true, color: template.muted },
    });
  });
}

function addAiNetworkVisual(spec, template, opts = {}) {
  const x = opts.x ?? 1120;
  const y = opts.y ?? 120;
  const w = opts.w ?? 650;
  const h = opts.h ?? 760;
  const dark = isDarkTemplate(template);
  const softAccent = mixColor(template.accent, template.surface, dark ? 0.74 : 0.86);
  const softAccent2 = mixColor(template.accent2, template.surface, dark ? 0.78 : 0.88);
  const scale = Math.min(w / 620, h / 780);
  const nodeSize = (size) => Math.max(18, Math.round(size * scale));
  addObject(spec, {
    id: 'visual-panel',
    type: 'shape',
    role: 'visual panel frame',
    x,
    y,
    w,
    h,
    z: 5,
    protected: false,
    style: { fill: template.surface, line: template.accent, lineWidth: 1.8, radius: 18, shape: 'roundRect' },
  });
  addObject(spec, {
    id: 'visual-wash-1',
    type: 'shape',
    role: 'visual ambient field',
    x: x + w * 0.09,
    y: y + h * 0.08,
    w: w * 0.82,
    h: h * 0.78,
    z: 5.2,
    decorative: true,
    protected: false,
    style: { fill: softAccent, line: softAccent, shape: 'roundRect', radius: 28, opacity: 0.28 },
  });
  addObject(spec, {
    id: 'visual-wash-2',
    type: 'shape',
    role: 'visual accent field',
    x: x + w * 0.36,
    y: y + h * 0.22,
    w: w * 0.5,
    h: h * 0.42,
    z: 5.3,
    decorative: true,
    protected: false,
    style: { fill: softAccent2, line: softAccent2, shape: 'roundRect', radius: 22, opacity: 0.24 },
  });

  const nodes = [
    [x + w * 0.2, y + h * 0.21, template.accent, nodeSize(68)],
    [x + w * 0.56, y + h * 0.15, template.accent2, nodeSize(56)],
    [x + w * 0.82, y + h * 0.34, template.accent3, nodeSize(62)],
    [x + w * 0.35, y + h * 0.49, template.accent2, nodeSize(58)],
    [x + w * 0.69, y + h * 0.6, template.accent, nodeSize(78)],
    [x + w * 0.25, y + h * 0.77, template.accent3, nodeSize(60)],
    [x + w * 0.81, y + h * 0.82, template.accent2, nodeSize(54)],
  ];
  const links = [[0, 1], [1, 2], [0, 3], [3, 4], [2, 4], [3, 5], [4, 6], [5, 6], [1, 4]];
  links.forEach(([a, b], idx) => {
    const from = nodes[a];
    const to = nodes[b];
    const lx = Math.min(from[0], to[0]);
    const ly = Math.min(from[1], to[1]);
    const lw = Math.max(1, Math.abs(to[0] - from[0]));
    const lh = Math.max(1, Math.abs(to[1] - from[1]));
    addObject(spec, {
      id: `network-link-${idx}`,
      type: 'shape',
      role: 'network link',
      x: lx,
      y: ly,
      w: lw,
      h: lh,
      z: 6,
      decorative: true,
      protected: false,
      style: { shape: 'line', line: mixColor(template.muted, template.surface, dark ? 0.25 : 0.5), lineWidth: Math.max(0.8, 1.4 * scale), flipH: (to[0] - from[0]) * (to[1] - from[1]) < 0 },
    });
  });
  nodes.forEach(([cx, cy, color, size], idx) => {
    addObject(spec, {
      id: `network-node-${idx}`,
      type: 'shape',
      role: 'network node',
      x: cx - size / 2,
      y: cy - size / 2,
      w: size,
      h: size,
      z: 8,
      decorative: true,
      protected: false,
      style: { fill: color, line: mixColor(color, template.surface, 0.35), lineWidth: 2, shape: 'ellipse', opacity: idx === 4 ? 0.96 : 0.82 },
    });
  });
  addObject(spec, {
    id: 'visual-core-label',
    type: 'textbox',
    role: 'visual AI core label',
    x: x + w * 0.69 - Math.max(36, 90 * scale) / 2,
    y: y + h * 0.6 - Math.max(24, 50 * scale) / 2,
    w: Math.max(36, 90 * scale),
    h: Math.max(24, 50 * scale),
    z: 9,
    text: 'AI',
    decorative: true,
    protected: false,
    style: { fontFace: template.headingFace, fontSizePt: Math.max(10, 20 * scale), bold: true, color: template.surface, align: 'center', lineHeight: 1 },
  });
  const caption = opts.caption === '' ? '' : (opts.caption || 'Signals, models, and automation linked into one operating layer');
  if (caption) {
    addObject(spec, {
      id: 'visual-caption',
      type: 'textbox',
      role: 'visual caption',
      x: x + 72,
      y: y + h - 108,
      w: w - 144,
      h: 56,
      z: 9,
      text: caption,
      style: { fontFace: template.fontFace, fontSizePt: 11, bold: true, color: template.accent, align: 'center', lineHeight: 1.1 },
    });
  }
}

function buildTitleSpec(slideData, index, ctx) {
  const { template, topic, totalSlides } = ctx;
  const spec = createSlideSpec(slideData, index, ctx);
  addBackground(spec, template);
  addBrand(spec, template, template.name === 'Venture Blueprint' ? 'AETHERIA / VENTURE BLUEPRINT' : `AETHERIA / ${template.name}`);
  addObject(spec, {
    id: 'kicker',
    type: 'textbox',
    role: 'cover kicker',
    x: 112,
    y: 164,
    w: 520,
    h: 34,
    z: 7,
    text: normalizeText(slideData.kicker || 'Presentation narrative'),
    style: { fontFace: template.fontFace, fontSizePt: 12.5, bold: true, color: readableColor(template, template.accent2, template.background) },
  });
  addObject(spec, {
    id: 'headline',
    type: 'textbox',
    role: 'cover headline',
    x: 112,
    y: 262,
    w: 910,
    h: 285,
    z: 7,
    text: normalizeText(slideData.title || topic),
    style: { fontFace: template.headingFace, fontSizePt: 51, bold: true, color: template.ink, lineHeight: 1.02 },
  });
  addObject(spec, {
    id: 'subtitle',
    type: 'textbox',
    role: 'cover subtitle',
    x: 118,
    y: 616,
    w: 820,
    h: 66,
    z: 7,
    text: normalizeText(slideData.subtitle || slideData.content || 'A concise, evidence-backed story built for decision making.'),
    style: { fontFace: template.fontFace, fontSizePt: 17.5, color: template.muted, lineHeight: 1.22 },
  });
  const fallbackMetrics = cleanBullets(slideData.bullets || slideData.points).slice(0, 3).map((item, i) => ({ value: `0${i + 1}`, label: item }));
  addMetricChips(spec, slideData.metrics || fallbackMetrics, template, { x: 112, y: 788, w: 960, h: 124, valueSizePt: 21, labelSizePt: 8.5 });
  addAiNetworkVisual(spec, template, {
    x: 1160,
    y: 126,
    w: 620,
    h: 780,
    caption: normalizeText(slideData.visual_summary || slideData.summary || 'A visual system for the story behind the deck'),
  });
  addFooter(spec, template, index, totalSlides, topic);
  return spec;
}

function buildContentSpec(slideData, index, ctx) {
  const { template, topic, totalSlides } = ctx;
  const spec = createSlideSpec(slideData, index, ctx);
  addBackground(spec, template);
  addBrand(spec, template, normalizeText(slideData.kicker || slideData.section || 'Strategic insight'));
  addObject(spec, {
    id: 'headline',
    type: 'textbox',
    role: 'slide headline',
    x: 112,
    y: 140,
    w: 1120,
    h: 108,
    z: 7,
    text: normalizeText(slideData.title),
    style: { fontFace: template.headingFace, fontSizePt: 31, bold: true, color: template.ink, lineHeight: 1.08 },
  });

  const hasChart = Boolean(slideData.chart);
  const hasTable = Boolean(slideData.table);
  const hasDiagram = Boolean(slideData.nodes || slideData.steps);
  const hasMetrics = Array.isArray(slideData.metrics) && slideData.metrics.length > 0;
  if (hasChart) {
    addObject(spec, {
      id: 'evidence-chart',
      type: 'chart',
      role: 'evidence chart',
      x: 150,
      y: 310,
      w: 1180,
      h: hasMetrics ? 430 : 520,
      z: 8,
      data: slideData.chart,
      style: { fill: template.surface, line: template.grid, radius: 14 },
    });
  } else if (hasTable) {
    addObject(spec, {
      id: 'structured-table',
      type: 'table',
      role: 'structured table',
      x: 145,
      y: 305,
      w: 1210,
      h: hasMetrics ? 430 : 545,
      z: 8,
      data: { rows: slideData.table },
      style: { fill: template.surface, line: template.grid, headerFill: template.accent, headerColor: 'FFFFFF' },
    });
  } else if (hasDiagram) {
    addObject(spec, {
      id: 'process-diagram',
      type: 'diagram',
      role: 'process diagram',
      x: 135,
      y: 360,
      w: 1250,
      h: 280,
      z: 8,
      data: { nodes: slideData.nodes || slideData.steps },
      style: { fill: template.surface, line: template.grid },
    });
  } else {
    const items = cleanBullets(slideData.bullets || slideData.content || slideData.points).slice(0, hasMetrics ? 3 : 4);
    items.forEach((item, i) => {
      const y = 318 + i * (hasMetrics ? 122 : 134);
      const accent = i === 1 ? template.accent2 : i === 2 ? template.accent3 : template.accent;
      addObject(spec, {
        id: `insight-card-${i + 1}`,
        type: 'shape',
        role: `insight card ${i + 1}`,
        x: 128,
        y,
        w: 940,
        h: hasMetrics ? 96 : 108,
        z: 8,
        protected: false,
        style: { fill: template.surface, line: accent, lineWidth: 1.4, radius: 12, shape: 'roundRect' },
      });
      addObject(spec, {
        id: `insight-number-${i + 1}`,
        type: 'textbox',
        role: `insight number ${i + 1}`,
        x: 165,
        y: y + 28,
        w: 58,
        h: 32,
        z: 9,
        text: String(i + 1).padStart(2, '0'),
        style: { fontFace: template.headingFace, fontSizePt: 14, bold: true, color: readableColor(template, accent, template.surface) },
      });
      addObject(spec, {
        id: `insight-text-${i + 1}`,
        type: 'textbox',
        role: `insight text ${i + 1}`,
        x: 245,
        y: y + 22,
        w: 760,
        h: hasMetrics ? 56 : 66,
        z: 9,
        text: item,
        style: { fontFace: template.fontFace, fontSizePt: hasMetrics ? 12 : 13, color: template.ink, lineHeight: 1.15 },
      });
    });
  }

  addObject(spec, {
    id: 'side-callout-card',
    type: 'shape',
    role: 'side callout card',
    x: 1430,
    y: 275,
    w: 350,
    h: 450,
    z: 7,
    protected: false,
    style: { fill: mixColor(template.surface, template.accent, isDarkTemplate(template) ? 0.08 : 0.04), line: template.accent, lineWidth: 1.2, radius: 16, shape: 'roundRect' },
  });
  addAiNetworkVisual(spec, template, { x: 1475, y: 318, w: 260, h: 280, caption: '' });
  addObject(spec, {
    id: 'side-callout',
    type: 'textbox',
    role: 'side callout',
    x: 1478,
    y: 618,
    w: 252,
    h: 70,
    z: 9,
    text: normalizeText(slideData.callout || slideData.summary || cleanBullets(slideData.bullets || slideData.content || slideData.points)[0] || 'The key idea should be visible at a glance.'),
    style: { fontFace: template.headingFace, fontSizePt: 14, bold: true, color: template.accent, align: 'center', lineHeight: 1.15 },
  });
  if (hasMetrics) {
    addMetricChips(spec, slideData.metrics, template, { x: 128, y: 800, w: 1230, h: 92, maxItems: 4, valueSizePt: 17, labelSizePt: 7.5 });
  }
  addFooter(spec, template, index, totalSlides, topic);
  return spec;
}

function buildTwoColumnSpec(slideData, index, ctx) {
  const { template, topic, totalSlides } = ctx;
  const spec = createSlideSpec(slideData, index, ctx);
  addBackground(spec, template);
  addBrand(spec, template, normalizeText(slideData.kicker || 'Comparison'));
  addObject(spec, {
    id: 'headline',
    type: 'textbox',
    role: 'comparison headline',
    x: 112,
    y: 140,
    w: 1440,
    h: 100,
    z: 7,
    text: normalizeText(slideData.title),
    style: { fontFace: template.headingFace, fontSizePt: 31, bold: true, color: template.ink },
  });
  const fallbackItems = cleanBullets(slideData.bullets || slideData.content || slideData.points);
  const midpoint = Math.ceil(fallbackItems.length / 2);
  const cols = [
    {
      id: 'left',
      x: 128,
      color: template.accent2,
      title: slideData.left_title || slideData.left?.title || 'Current state',
      content: slideData.left_content || slideData.left_bullets || slideData.left?.content || slideData.left?.bullets || fallbackItems.slice(0, midpoint),
    },
    {
      id: 'right',
      x: 988,
      color: template.accent3,
      title: slideData.right_title || slideData.right?.title || 'Target state',
      content: slideData.right_content || slideData.right_bullets || slideData.right?.content || slideData.right?.bullets || fallbackItems.slice(midpoint),
    },
  ];
  cols.forEach((col, colIndex) => {
    addObject(spec, {
      id: `${col.id}-panel`,
      type: 'shape',
      role: `${col.title} panel`,
      x: col.x,
      y: 310,
      w: 750,
      h: 520,
      z: 8,
      protected: false,
      style: { fill: template.surface, line: col.color, lineWidth: 1.7, radius: 16, shape: 'roundRect' },
    });
    addObject(spec, {
      id: `${col.id}-title`,
      type: 'textbox',
      role: `${col.title} title`,
      x: col.x + 48,
      y: 360,
      w: 610,
      h: 44,
      z: 9,
      text: normalizeText(col.title),
      style: { fontFace: template.headingFace, fontSizePt: 20, bold: true, color: readableColor(template, col.color, template.surface) },
    });
    cleanBullets(col.content).slice(0, 4).forEach((item, i) => {
      const y = 452 + i * 78;
      addObject(spec, {
        id: `${col.id}-bullet-dot-${i + 1}`,
        type: 'shape',
        role: `${col.title} bullet marker`,
        x: col.x + 56,
        y: y + 10,
        w: 13,
        h: 13,
        z: 9,
        decorative: true,
        protected: false,
        style: { fill: col.color, shape: 'ellipse' },
      });
      addObject(spec, {
        id: `${col.id}-bullet-${i + 1}`,
        type: 'textbox',
        role: `${col.title} bullet ${i + 1}`,
        x: col.x + 92,
        y,
        w: 585,
        h: 48,
        z: 9,
        text: item,
        style: { fontFace: template.fontFace, fontSizePt: 12, color: template.ink, lineHeight: 1.18 },
      });
    });
    addObject(spec, {
      id: `${col.id}-index`,
      type: 'textbox',
      role: `${col.title} index`,
      x: col.x + 622,
      y: 740,
      w: 62,
      h: 36,
      z: 9,
      protected: false,
      text: String(colIndex + 1).padStart(2, '0'),
      style: { fontFace: template.headingFace, fontSizePt: 14, bold: true, color: readableColor(template, col.color, template.surface), align: 'right' },
    });
  });
  addFooter(spec, template, index, totalSlides, topic);
  return spec;
}

function buildImageSpec(slideData, index, ctx) {
  const { template, topic, totalSlides } = ctx;
  const spec = createSlideSpec(slideData, index, ctx);
  addBackground(spec, template);
  addBrand(spec, template, normalizeText(slideData.kicker || 'Visual explanation'));
  addObject(spec, {
    id: 'headline',
    type: 'textbox',
    role: 'visual headline',
    x: 112,
    y: 142,
    w: 710,
    h: 128,
    z: 7,
    text: normalizeText(slideData.title),
    style: { fontFace: template.headingFace, fontSizePt: 33, bold: true, color: template.ink, lineHeight: 1.05 },
  });
  const imagePath = slideData.image_path || slideData.imagePath;
  if (imagePath && fs.existsSync(imagePath)) {
    addObject(spec, {
      id: 'main-image',
      type: 'image',
      role: 'main visual image',
      x: 860,
      y: 128,
      w: 900,
      h: 710,
      z: 8,
      data: { imagePath },
      style: { line: template.accent, radius: 18 },
    });
  } else {
    addAiNetworkVisual(spec, template, {
      x: 860,
      y: 128,
      w: 900,
      h: 710,
      caption: normalizeText(slideData.visual_summary || slideData.summary || 'A generated explanatory visual tuned to the slide topic'),
    });
  }
  const points = cleanBullets(slideData.bullets || slideData.points || slideData.content).slice(0, 4);
  points.forEach((item, i) => {
    addObject(spec, {
      id: `support-point-${i + 1}`,
      type: 'textbox',
      role: `support point ${i + 1}`,
      x: 132,
      y: 340 + i * 90,
      w: 600,
      h: 56,
      z: 8,
      text: item,
      style: { fontFace: template.fontFace, fontSizePt: 13, color: template.muted, lineHeight: 1.2 },
    });
  });
  addFooter(spec, template, index, totalSlides, topic);
  return spec;
}

function buildHtmlSpec(slideData, index, ctx) {
  const spec = createSlideSpec(slideData, index, ctx);
  spec.type = 'html';
  const parsed = parseContractHtml(slideData.html || slideData.contract_html || '', ctx.template);
  spec.objects = parsed.objects;
  spec.contract_warnings = parsed.warnings;
  return spec;
}

function buildSlideSpec(slideData, index, ctx) {
  const type = slideType(slideData);
  if (type === 'html') return buildHtmlSpec(slideData, index, ctx);
  if (type === 'title') return buildTitleSpec(slideData, index, ctx);
  if (type === 'two_column') return buildTwoColumnSpec(slideData, index, ctx);
  if (type === 'image') return buildImageSpec(slideData, index, ctx);
  return buildContentSpec(slideData, index, ctx);
}

function boxesOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function isContained(inner, outer, tolerance = 2) {
  return inner.x >= outer.x - tolerance && inner.y >= outer.y - tolerance &&
    inner.x + inner.w <= outer.x + outer.w + tolerance &&
    inner.y + inner.h <= outer.y + outer.h + tolerance;
}

function estimateTextCapacity(object) {
  const style = object.style || {};
  const sizePx = fontPx(style.fontSizePt || 12);
  const lineHeight = sizePx * (style.lineHeight || 1.16);
  const charWidth = sizePx * (style.bold ? 0.54 : 0.49);
  const lines = Math.max(1, Math.floor(object.h / Math.max(lineHeight, 1)));
  const charsPerLine = Math.max(5, Math.floor(object.w / Math.max(charWidth, 1)));
  return Math.floor(lines * charsPerLine * 1.08);
}

function findBackgroundForText(object, objects, template) {
  const center = { x: object.x + object.w / 2, y: object.y + object.h / 2 };
  const candidates = objects
    .filter((candidate) => candidate.type === 'shape' && candidate.z <= object.z && candidate.style?.fill)
    .filter((candidate) => center.x >= candidate.x && center.x <= candidate.x + candidate.w && center.y >= candidate.y && center.y <= candidate.y + candidate.h)
    .sort((a, b) => b.z - a.z);
  return candidates[0]?.style?.fill || template.background;
}

function validateDeck(deck) {
  const audits = deck.slides.map((slide) => {
    const warnings = Array.isArray(slide.contract_warnings) ? slide.contract_warnings.slice() : [];
    const objects = slide.objects.slice().sort((a, b) => a.z - b.z);
    objects.forEach((object) => {
      if (object.x < 0 || object.y < 0 || object.x + object.w > CANVAS_W || object.y + object.h > CANVAS_H) {
        warnings.push({
          type: 'out_of_bounds',
          severity: 'error',
          object_id: object.id,
          role: object.role,
          message: `${object.role} extends outside the 1920x1080 canvas.`,
        });
      }
      if (object.type === 'textbox') {
        const chars = normalizeText(object.text).replace(/\s+/g, ' ').trim().length;
        const capacity = estimateTextCapacity(object);
        if (chars > capacity) {
          warnings.push({
            type: 'text_overflow',
            severity: chars > capacity * 1.25 ? 'error' : 'warning',
            object_id: object.id,
            role: object.role,
            chars,
            capacity,
            message: `${object.role} may overflow: ${chars} chars for about ${capacity} chars of space.`,
          });
        }
        const bg = findBackgroundForText(object, objects, slide.template);
        const color = object.style?.color || slide.template.ink;
        const ratio = contrastRatio(color, bg);
        if (ratio < 3.8) {
          warnings.push({
            type: 'low_contrast',
            severity: 'warning',
            object_id: object.id,
            role: object.role,
            contrast: Number(ratio.toFixed(2)),
            message: `${object.role} has low contrast (${ratio.toFixed(2)}:1).`,
          });
        }
      }
    });

    const protectedObjects = objects.filter((object) => object.protected && !object.decorative && object.type !== 'shape');
    for (let i = 0; i < protectedObjects.length; i += 1) {
      for (let j = i + 1; j < protectedObjects.length; j += 1) {
        const a = protectedObjects[i];
        const b = protectedObjects[j];
        if (boxesOverlap(a, b) && !isContained(a, b) && !isContained(b, a)) {
          warnings.push({
            type: 'region_overlap',
            severity: 'error',
            object_id: a.id,
            with_object_id: b.id,
            role: a.role,
            with: b.role,
            message: `${a.role} overlaps ${b.role}.`,
          });
        }
      }
    }
    return {
      slide_index: slide.index,
      title: slide.title,
      object_count: objects.length,
      warnings,
    };
  });
  return {
    ok: !audits.some((audit) => audit.warnings.some((warning) => warning.severity === 'error')),
    warning_count: audits.reduce((sum, audit) => sum + audit.warnings.length, 0),
    audits,
  };
}

function repairDeck(deck, validation) {
  const bySlide = new Map(deck.slides.map((slide) => [slide.index, slide]));
  let changed = 0;
  validation.audits.forEach((audit) => {
    const slide = bySlide.get(audit.slide_index);
    if (!slide) return;
    audit.warnings.forEach((warning) => {
      const object = slide.objects.find((candidate) => candidate.id === warning.object_id);
      if (!object) return;
      if (warning.severity !== 'error') return;
      if (warning.type === 'text_overflow' && object.type === 'textbox') {
        const current = Number(object.style.fontSizePt || 12);
        const next = Math.max(7.5, Math.round(current * 0.9 * 10) / 10);
        if (next < current) {
          object.style.fontSizePt = next;
          object.style.lineHeight = Math.max(1.02, Number(object.style.lineHeight || 1.15) * 0.97);
          changed += 1;
        }
      }
      if (warning.type === 'out_of_bounds') {
        object.x = Math.max(0, Math.min(object.x, CANVAS_W - object.w));
        object.y = Math.max(0, Math.min(object.y, CANVAS_H - object.h));
        changed += 1;
      }
    });
  });
  return changed;
}

function escapeHtml(value) {
  return normalizeText(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function cssColor(color) {
  return `#${safeColor(color, '000000')}`;
}

function objectStyle(object) {
  const style = object.style || {};
  const rules = [
    'position:absolute',
    `left:${object.x}px`,
    `top:${object.y}px`,
    `width:${object.w}px`,
    `height:${object.h}px`,
    `z-index:${object.z}`,
    'box-sizing:border-box',
  ];
  if (object.type === 'textbox') {
    const fontFace = style.fontFace || BODY_FONT;
    rules.push(`font-family:'${fontFace}','Segoe UI',Arial,sans-serif`);
    rules.push(`font-size:${fontPx(style.fontSizePt || 12)}px`);
    rules.push(`line-height:${style.lineHeight || 1.12}`);
    rules.push(`font-weight:${style.bold ? 800 : 400}`);
    rules.push(`color:${cssColor(style.color || '000000')}`);
    rules.push(`text-align:${style.align || 'left'}`);
    rules.push('overflow:visible');
    rules.push('white-space:pre-wrap');
  } else {
    if (style.fill) rules.push(`background:${cssColor(style.fill)}`);
    if (style.opacity != null) rules.push(`opacity:${style.opacity}`);
    if (style.line) rules.push(`border:${style.lineWidth || 1}px solid ${cssColor(style.line)}`);
    if (style.radius) rules.push(`border-radius:${style.radius}px`);
  }
  return rules.join(';');
}

function renderHtmlObject(object) {
  const attrs = `data-object="true" data-object-type="${escapeHtml(object.type)}" data-object-id="${escapeHtml(object.id)}"`;
  if (object.type === 'textbox') {
    return `<div ${attrs} style="${objectStyle(object)}">${escapeHtml(object.text || '')}</div>`;
  }
  if (object.type === 'chart') {
    const series = parseChartData(object.data) || [];
    const first = series[0] || { labels: [], values: [] };
    const max = Math.max(...first.values.map((value) => Number(value) || 0), 1);
    const bars = first.labels.slice(0, 6).map((label, idx) => {
      const value = Number(first.values[idx] || 0);
      const width = Math.max(4, Math.round((value / max) * 100));
      return `<div class="chart-row"><span>${escapeHtml(label)}</span><i style="width:${width}%"></i><b>${escapeHtml(String(value))}</b></div>`;
    }).join('');
    return `<div ${attrs} class="chart-object" style="${objectStyle(object)}">${bars}</div>`;
  }
  if (object.type === 'table') {
    const rows = normalizeTableRows(object.data?.rows).slice(0, 8);
    const htmlRows = rows.map((row, idx) => `<div class="table-row ${idx === 0 ? 'header' : ''}">${row.map((cell) => `<span>${escapeHtml(cell)}</span>`).join('')}</div>`).join('');
    return `<div ${attrs} class="table-object" style="${objectStyle(object)}">${htmlRows}</div>`;
  }
  if (object.type === 'diagram') {
    const nodes = normalizeNodes(object.data?.nodes).slice(0, 5);
    return `<div ${attrs} class="diagram-object" style="${objectStyle(object)}">${nodes.map((node, idx) => `<span><b>${idx + 1}</b>${escapeHtml(node.title || node.name || node)}</span>`).join('')}</div>`;
  }
  if (object.type === 'image' && object.data?.imagePath) {
    const src = pathToFileUrl(object.data.imagePath);
    return `<img ${attrs} src="${src}" style="${objectStyle(object)};object-fit:cover" />`;
  }
  if (object.style?.shape === 'line') {
    const transform = object.style.flipH ? 'scaleX(-1)' : 'none';
    return `<div ${attrs} style="${objectStyle(object)};background:transparent;border:0;border-top:${object.style.lineWidth || 1}px solid ${cssColor(object.style.line || '000000')};transform:${transform};transform-origin:left top"></div>`;
  }
  return `<div ${attrs} style="${objectStyle(object)}"></div>`;
}

function renderSlideHtml(slide) {
  const objects = slide.objects.slice().sort((a, b) => a.z - b.z).map(renderHtmlObject).join('\n');
  const notesTemplate = slide.notes
    ? `\n<template data-slide-notes>${escapeHtml(slide.notes)}</template>`
    : '';
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=${CANVAS_W}, initial-scale=1">
<style>
html,body{margin:0;width:${CANVAS_W}px;height:${CANVAS_H}px;background:#fff;overflow:hidden}
.slide-container{position:relative;width:${CANVAS_W}px;height:${CANVAS_H}px;overflow:hidden;background:${cssColor(slide.template.background)}}
.chart-object{padding:44px 48px;display:flex;flex-direction:column;gap:22px}
.chart-row{display:grid;grid-template-columns:190px 1fr 80px;align-items:center;gap:20px;font:600 18px 'Segoe UI',Arial,sans-serif;color:${cssColor(slide.template.muted)}}
.chart-row i{display:block;height:22px;border-radius:999px;background:${cssColor(slide.template.accent)}}
.chart-row:nth-child(2n) i{background:${cssColor(slide.template.accent2)}}
.chart-row b{font-weight:800;color:${cssColor(slide.template.ink)}}
.table-object{display:flex;flex-direction:column;overflow:hidden;border-radius:14px}
.table-row{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;min-height:52px}
.table-row span{padding:14px 16px;border-right:1px solid ${cssColor(slide.template.grid)};border-bottom:1px solid ${cssColor(slide.template.grid)};font:600 16px 'Segoe UI',Arial,sans-serif;color:${cssColor(slide.template.ink)}}
.table-row.header span{background:${cssColor(slide.template.accent)};color:#fff;font-weight:800}
.diagram-object{display:flex;align-items:center;gap:26px;background:transparent!important;border:0!important}
.diagram-object span{flex:1;min-height:120px;padding:28px 20px;border-radius:16px;background:${cssColor(slide.template.surface)};border:1.4px solid ${cssColor(slide.template.accent)};font:700 17px 'Segoe UI',Arial,sans-serif;color:${cssColor(slide.template.ink)}}
.diagram-object b{display:block;margin-bottom:16px;color:${cssColor(slide.template.accent2)}}
</style>
</head>
<body>
<div class="slide-container">
${objects}
</div>
${notesTemplate}
</body>
</html>`;
}

function pathToFileUrl(filePath) {
  const resolved = path.resolve(filePath).replace(/\\/g, '/');
  return `file:///${resolved.replace(/^\/+/, '')}`;
}

function writeHtmlDeck(deck, outDir) {
  const deckDir = path.join(outDir, `${deck.slug}.slides`);
  const slidesDir = path.join(deckDir, 'slides');
  const assetsDir = path.join(deckDir, 'assets');
  fs.mkdirSync(slidesDir, { recursive: true });
  fs.mkdirSync(assetsDir, { recursive: true });
  const manifest = {
    canvas: { width: CANVAS_W, height: CANVAS_H },
    template: deck.template.id,
    playlist: [],
    slides: [],
  };
  deck.slides.forEach((slide) => {
    const fileName = `slide-${String(slide.index).padStart(2, '0')}.html`;
    const filePath = path.join(slidesDir, fileName);
    fs.writeFileSync(filePath, renderSlideHtml(slide), 'utf8');
    manifest.playlist.push(`slides/${fileName}`);
    manifest.slides.push({ id: slide.id, title: slide.title, file: `slides/${fileName}`, has_notes: Boolean(slide.notes) });
  });
  fs.writeFileSync(path.join(deckDir, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf8');
  return { deckDir, slidesDir, assetsDir, manifestPath: path.join(deckDir, 'manifest.json') };
}

function findBrowserExecutable() {
  const candidates = [
    process.env.PUPPETEER_EXECUTABLE_PATH,
    process.env.CHROME_PATH,
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

async function renderHtmlPreviews(deck, htmlDeck) {
  const previewDir = path.join(htmlDeck.deckDir, 'previews');
  fs.mkdirSync(previewDir, { recursive: true });
  const executablePath = findBrowserExecutable();
  if (!executablePath) {
    return {
      ok: false,
      warning: 'No Chromium or Edge executable found, skipped screenshot verification.',
      previews: [],
      audits: [],
    };
  }
  let puppeteer;
  try {
    puppeteer = require('puppeteer-core');
  } catch (error) {
    return {
      ok: false,
      warning: `puppeteer-core unavailable: ${error.message}`,
      previews: [],
      audits: [],
    };
  }

  const browser = await puppeteer.launch({
    executablePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--font-render-hinting=none'],
  });
  const previews = [];
  const audits = [];
  try {
    for (const slide of deck.slides) {
      const page = await browser.newPage();
      await page.setViewport({ width: CANVAS_W, height: CANVAS_H, deviceScaleFactor: 1 });
      const htmlPath = path.join(htmlDeck.slidesDir, `slide-${String(slide.index).padStart(2, '0')}.html`);
      await page.goto(pathToFileUrl(htmlPath), { waitUntil: 'networkidle0', timeout: 15000 });
      await page.evaluateHandle('document.fonts ? document.fonts.ready : Promise.resolve()');
      const renderAudit = await page.evaluate(() => {
        const container = document.querySelector('.slide-container');
        const canvas = container.getBoundingClientRect();
        const warnings = [];
        const objects = Array.from(document.querySelectorAll('[data-object="true"]')).map((node) => {
          const rect = node.getBoundingClientRect();
          const type = node.getAttribute('data-object-type');
          const id = node.getAttribute('data-object-id');
          const overflow = type === 'textbox' && (node.scrollHeight > node.clientHeight + 2 || node.scrollWidth > node.clientWidth + 2);
          if (overflow) {
            warnings.push({
              type: 'rendered_text_overflow',
              severity: 'error',
              object_id: id,
              message: `${id} overflows after browser render.`,
            });
          }
          if (rect.left < canvas.left - 1 || rect.top < canvas.top - 1 || rect.right > canvas.right + 1 || rect.bottom > canvas.bottom + 1) {
            warnings.push({
              type: 'rendered_out_of_bounds',
              severity: 'error',
              object_id: id,
              message: `${id} is outside the rendered canvas.`,
            });
          }
          return {
            id,
            type,
            x: Math.round(rect.left - canvas.left),
            y: Math.round(rect.top - canvas.top),
            w: Math.round(rect.width),
            h: Math.round(rect.height),
          };
        });
        return { objects, warnings };
      });
      const screenshotPath = path.join(previewDir, `slide-${String(slide.index).padStart(2, '0')}.jpg`);
      const buffer = await page.screenshot({ path: screenshotPath, type: 'jpeg', quality: 86, fullPage: false });
      previews.push({
        slide_index: slide.index,
        path: screenshotPath,
        data_uri: `data:image/jpeg;base64,${buffer.toString('base64')}`,
      });
      audits.push({
        slide_index: slide.index,
        title: slide.title,
        rendered_object_count: renderAudit.objects.length,
        warnings: renderAudit.warnings,
      });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return {
    ok: !audits.some((audit) => audit.warnings.some((warning) => warning.severity === 'error')),
    warning: null,
    previews,
    audits,
  };
}

function setupPptx(payload) {
  const pptx = new PptxGenJS();
  currentPptx = pptx;
  pptx.author = 'Aetheria ai';
  pptx.company = 'Aetheria ai';
  pptx.subject = normalizeText(payload.topic || 'AI generated presentation');
  pptx.title = normalizeText(payload.topic || 'Presentation');
  pptx.lang = 'en-US';
  pptx.defineLayout({ name: 'AETHERIA_WIDE', width: SLIDE_W_IN, height: SLIDE_H_IN });
  pptx.layout = 'AETHERIA_WIDE';
  pptx.theme = {
    headFontFace: HEADING_FONT,
    bodyFontFace: BODY_FONT,
    lang: 'en-US',
  };
  return pptx;
}

function pptShapeType(shape) {
  const type = String(shape || 'rect');
  if (type === 'roundRect') return currentPptx.ShapeType.roundRect;
  if (type === 'ellipse') return currentPptx.ShapeType.ellipse;
  if (type === 'line') return currentPptx.ShapeType.line;
  return currentPptx.ShapeType.rect;
}

function pptColor(color, fallback = '000000') {
  return safeColor(color, fallback);
}

function renderShape(slide, object) {
  const style = object.style || {};
  if (style.shape === 'line') {
    slide.addShape(currentPptx.ShapeType.line, {
      x: toIn(object.x),
      y: toIn(object.y),
      w: toIn(object.w),
      h: toIn(object.h),
      flipH: Boolean(style.flipH),
      line: { color: pptColor(style.line || style.fill, '000000'), transparency: style.opacity != null ? Math.round((1 - style.opacity) * 100) : 0, width: style.lineWidth || 1 },
    });
    return;
  }
  slide.addShape(pptShapeType(style.shape), {
    x: toIn(object.x),
    y: toIn(object.y),
    w: toIn(object.w),
    h: toIn(object.h),
    rectRadius: style.radius ? toIn(style.radius) : undefined,
    fill: style.fill ? { color: pptColor(style.fill), transparency: style.opacity != null ? Math.round((1 - style.opacity) * 100) : 0 } : { transparency: 100 },
    line: style.line ? { color: pptColor(style.line), width: style.lineWidth || 1 } : null,
  });
}

function renderText(slide, object) {
  const style = object.style || {};
  slide.addText(normalizeText(object.text), {
    x: toIn(object.x),
    y: toIn(object.y),
    w: toIn(object.w),
    h: toIn(object.h),
    fontFace: style.fontFace || BODY_FONT,
    fontSize: style.fontSizePt || 12,
    bold: Boolean(style.bold),
    italic: Boolean(style.italic),
    color: pptColor(style.color || '000000'),
    align: style.align || 'left',
    valign: style.valign || 'top',
    margin: 0.02,
    breakLine: false,
    fit: 'shrink',
    charSpace: style.letterSpacing || 0,
    paraSpaceAfterPt: style.paraSpaceAfterPt || 0,
  });
}

function parseChartData(chart) {
  if (!chart) return null;
  const chartData = chart.data || chart;
  if (!chartData) return null;
  if (Array.isArray(chartData) && chartData.length > 0 && Array.isArray(chartData[0])) {
    const headers = chartData[0];
    const rows = chartData.slice(1);
    if (headers.length < 2 || rows.length === 0) return null;
    const labels = rows.map((row) => String(row[0] || ''));
    const series = [];
    for (let col = 1; col < headers.length; col += 1) {
      series.push({
        name: String(headers[col] || `Series ${col}`),
        labels,
        values: rows.map((row) => Number(row[col]) || 0),
      });
    }
    return series;
  }
  if (Array.isArray(chartData) && chartData.length > 0 && typeof chartData[0] === 'object') {
    if (chartData[0].labels && chartData[0].values) {
      return chartData.map((series) => ({
        name: String(series.name || series.series || 'Series'),
        labels: Array.isArray(series.labels) ? series.labels.map(String) : [],
        values: Array.isArray(series.values) ? series.values.map((value) => Number(value) || 0) : [],
      }));
    }
    return [{
      name: String(chart.title || 'Value'),
      labels: chartData.map((item) => String(item.label || item.name || item.category || '')),
      values: chartData.map((item) => Number(item.value || item.val || 0) || 0),
    }];
  }
  return null;
}

function renderChart(slide, object, template) {
  renderShape(slide, { ...object, type: 'shape', style: { fill: object.style?.fill || template.surface, line: object.style?.line || template.grid, radius: 14, shape: 'roundRect' } });
  const chartData = parseChartData(object.data);
  if (!chartData) return;
  const chartType = String(object.data?.chart_type || object.data?.type || 'bar').toLowerCase();
  let pptxChartType = currentPptx.ChartType.bar;
  if (chartType === 'line') pptxChartType = currentPptx.ChartType.line;
  else if (chartType === 'pie') pptxChartType = currentPptx.ChartType.pie;
  else if (chartType === 'doughnut') pptxChartType = currentPptx.ChartType.doughnut;
  else if (chartType === 'area') pptxChartType = currentPptx.ChartType.area;
  slide.addChart(pptxChartType, chartData, {
    x: toIn(object.x + 56),
    y: toIn(object.y + 52),
    w: toIn(object.w - 112),
    h: toIn(object.h - 96),
    title: object.data?.title || object.data?.name || '',
    showTitle: Boolean(object.data?.title || object.data?.name),
    titleColor: template.ink,
    titleFontFace: template.headingFace,
    titleFontSize: 13,
    chartColors: [template.accent, template.accent2, template.accent3],
    showLegend: chartData.length > 1 || chartType === 'pie' || chartType === 'doughnut',
    legendColor: template.muted,
    legendFontFace: template.fontFace,
    legendFontSize: 9,
    catAxisLabelColor: template.muted,
    catAxisLabelFontFace: template.fontFace,
    catAxisLabelFontSize: 8,
    valAxisLabelColor: template.muted,
    valAxisLabelFontFace: template.fontFace,
    valAxisLabelFontSize: 8,
    barDir: chartType === 'bar' ? 'bar' : 'col',
  });
}

function normalizeTableRows(rows) {
  const tableRows = Array.isArray(rows) ? rows.slice(0, 8) : [];
  return tableRows.map((row) => Array.isArray(row) ? row.map((cell) => normalizeText(cell)) : Object.values(row || {}).map((cell) => normalizeText(cell)));
}

function renderTable(slide, object, template) {
  const rows = normalizeTableRows(object.data?.rows);
  if (!rows.length) return;
  const colCount = Math.max(...rows.map((row) => row.length), 1);
  const rowH = object.h / rows.length;
  const colW = object.w / colCount;
  rows.forEach((row, r) => {
    for (let c = 0; c < colCount; c += 1) {
      const isHeader = r === 0;
      const cell = {
        x: object.x + c * colW,
        y: object.y + r * rowH,
        w: colW,
        h: rowH,
      };
      slide.addShape(currentPptx.ShapeType.rect, {
        x: toIn(cell.x),
        y: toIn(cell.y),
        w: toIn(cell.w),
        h: toIn(cell.h),
        fill: { color: isHeader ? template.accent : template.surface },
        line: { color: template.grid, width: 0.5 },
      });
      slide.addText(normalizeText(row[c] ?? ''), {
        x: toIn(cell.x + 14),
        y: toIn(cell.y + 12),
        w: toIn(cell.w - 28),
        h: toIn(cell.h - 18),
        fontFace: template.fontFace,
        fontSize: isHeader ? 9 : 8.5,
        bold: isHeader,
        color: isHeader ? 'FFFFFF' : template.ink,
        margin: 0,
        fit: 'shrink',
      });
    }
  });
}

function normalizeNodes(nodes) {
  return Array.isArray(nodes) ? nodes : [];
}

function renderDiagram(slide, object, template) {
  const nodes = normalizeNodes(object.data?.nodes).slice(0, 5);
  if (!nodes.length) return;
  const gap = 24;
  const boxW = (object.w - gap * (nodes.length - 1)) / nodes.length;
  nodes.forEach((node, idx) => {
    const x = object.x + idx * (boxW + gap);
    slide.addShape(currentPptx.ShapeType.roundRect, {
      x: toIn(x),
      y: toIn(object.y),
      w: toIn(boxW),
      h: toIn(object.h),
      rectRadius: toIn(12),
      fill: { color: template.surface },
      line: { color: idx % 2 ? template.accent2 : template.accent, width: 1 },
    });
    slide.addText(String(idx + 1).padStart(2, '0'), {
      x: toIn(x + 20),
      y: toIn(object.y + 22),
      w: toIn(boxW - 40),
      h: toIn(28),
      fontFace: template.headingFace,
      fontSize: 11,
      bold: true,
      color: idx % 2 ? template.accent2 : template.accent,
      margin: 0,
    });
    slide.addText(normalizeText(node.title || node.name || node), {
      x: toIn(x + 20),
      y: toIn(object.y + 70),
      w: toIn(boxW - 40),
      h: toIn(58),
      fontFace: template.fontFace,
      fontSize: 10,
      bold: true,
      color: template.ink,
      margin: 0,
      fit: 'shrink',
    });
    slide.addText(normalizeText(node.detail || node.description || ''), {
      x: toIn(x + 20),
      y: toIn(object.y + 140),
      w: toIn(boxW - 40),
      h: toIn(80),
      fontFace: template.fontFace,
      fontSize: 8,
      color: template.muted,
      margin: 0,
      fit: 'shrink',
    });
  });
}

function renderImage(slide, object, template) {
  renderShape(slide, { ...object, type: 'shape', style: { fill: template.surface, line: object.style?.line || template.accent, radius: object.style?.radius || 16, shape: 'roundRect' } });
  const imagePath = object.data?.imagePath;
  if (imagePath && fs.existsSync(imagePath)) {
    slide.addImage({
      path: imagePath,
      x: toIn(object.x + 12),
      y: toIn(object.y + 12),
      w: toIn(object.w - 24),
      h: toIn(object.h - 24),
      sizingCrop: true,
    });
  }
}

function renderDeckToPptx(deck, payload) {
  const pptx = setupPptx(payload);
  deck.slides.forEach((slideSpec) => {
    const slide = pptx.addSlide();
    slide.background = { color: slideSpec.template.background };
    slideSpec.objects.slice().sort((a, b) => a.z - b.z).forEach((object) => {
      if (object.type === 'textbox') renderText(slide, object);
      else if (object.type === 'chart') renderChart(slide, object, slideSpec.template);
      else if (object.type === 'table') renderTable(slide, object, slideSpec.template);
      else if (object.type === 'diagram') renderDiagram(slide, object, slideSpec.template);
      else if (object.type === 'image') renderImage(slide, object, slideSpec.template);
      else renderShape(slide, object);
    });
    if (slideSpec.notes) {
      slide.addNotes(slideSpec.notes);
    }
  });
  return pptx;
}

function makeSlug(value) {
  return normalizeText(value || 'presentation')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80) || 'presentation';
}

function buildDeck(payload) {
  const template = pickTemplate(payload.template);
  const topic = normalizeText(payload.topic || 'Presentation');
  const rawSlides = Array.isArray(payload.slides) && payload.slides.length
    ? payload.slides
    : [{ type: 'title', title: topic }, { type: 'content', title: 'Key points', bullets: cleanBullets(payload.content || '') }];
  const slides = rawSlides.map((slide, index) => normalizeSlide(slide, index, topic));
  const deck = {
    slug: makeSlug(topic),
    topic,
    template: { id: payload.template || 'aetheria_modern', ...template },
    slides: [],
  };
  slides.forEach((slideData, idx) => {
    deck.slides.push(buildSlideSpec(slideData, idx + 1, {
      template,
      topic,
      totalSlides: slides.length,
    }));
  });
  return { deck, normalizedSlides: slides, template };
}

async function main() {
  const lintOnly = process.argv[2] === '--lint';
  const payloadPath = lintOnly ? process.argv[3] : process.argv[2];
  if (!payloadPath) throw new Error('Usage: node ppt_harness_renderer.js [--lint] <payload.json>');
  const payload = readJson(payloadPath);
  if (lintOnly) {
    const { deck, normalizedSlides, template } = buildDeck(payload);
    const layoutValidation = validateDeck(deck);
    writeJson({
      ok: layoutValidation.ok,
      mode: 'lint',
      canvas: { width: CANVAS_W, height: CANVAS_H },
      template: { id: payload.template || 'aetheria_modern', name: template.name },
      layout_validation: layoutValidation,
      slides: normalizedSlides.map((slide, index) => ({
        index: index + 1,
        type: slideType(slide),
        title: slide.title,
        object_count: deck.slides[index]?.objects?.length || 0,
      })),
    });
    return;
  }
  if (!payload.output_path) throw new Error('payload.output_path is required');
  fs.mkdirSync(path.dirname(payload.output_path), { recursive: true });

  const { deck, normalizedSlides, template } = buildDeck(payload);
  const harnessDir = path.join(path.dirname(payload.output_path), 'presentation-harness');
  fs.mkdirSync(harnessDir, { recursive: true });

  let layoutValidation = validateDeck(deck);
  let repairCount = 0;
  for (let i = 0; i < 2 && !layoutValidation.ok; i += 1) {
    const changed = repairDeck(deck, layoutValidation);
    repairCount += changed;
    if (!changed) break;
    layoutValidation = validateDeck(deck);
  }

  const htmlDeck = writeHtmlDeck(deck, harnessDir);
  const renderValidation = await renderHtmlPreviews(deck, htmlDeck);
  if (!renderValidation.ok && renderValidation.audits.length) {
    const renderedAsLayout = {
      audits: renderValidation.audits.map((audit) => ({
        slide_index: audit.slide_index,
        warnings: audit.warnings.map((warning) => ({
          ...warning,
          type: warning.type === 'rendered_text_overflow' ? 'text_overflow' : warning.type,
        })),
      })),
    };
    repairCount += repairDeck(deck, renderedAsLayout);
    if (repairCount > 0) {
      writeHtmlDeck(deck, harnessDir);
    }
  }

  const pptx = renderDeckToPptx(deck, payload);
  await pptx.writeFile({ fileName: payload.output_path });
  const stat = fs.statSync(payload.output_path);

  const previewBySlide = new Map((renderValidation.previews || []).map((preview) => [preview.slide_index, preview]));
  writeJson({
    ok: true,
    output_path: payload.output_path,
    mime_type: PPTX_MIME,
    size: stat.size,
    harness: {
      version: 1,
      canvas: { width: CANVAS_W, height: CANVAS_H },
      pptx_size_inches: { width: SLIDE_W_IN, height: SLIDE_H_IN },
      html_deck_dir: htmlDeck.deckDir,
      manifest_path: htmlDeck.manifestPath,
      screenshot_validation: {
        ok: renderValidation.ok,
        warning: renderValidation.warning,
        warning_count: (renderValidation.audits || []).reduce((count, audit) => count + audit.warnings.length, 0),
        audits: renderValidation.audits || [],
      },
      repair_count: repairCount,
    },
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
    layout_validation: layoutValidation,
    slides: normalizedSlides.map((slide, index) => {
      const preview = previewBySlide.get(index + 1);
      return {
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
        preview_path: preview?.path || null,
        preview_data_uri: preview?.data_uri || null,
      };
    }),
  });
}

main().catch((error) => {
  writeJson({ ok: false, error: error.message, stack: error.stack });
  process.exitCode = 1;
});




