const $ = (selector) => document.querySelector(selector);
const chart = $('#history-chart');
let measurements = [];

function formatDate(value, options = {}) {
  return new Intl.DateTimeFormat('es', { dateStyle: 'medium', timeStyle: 'short', ...options }).format(new Date(value));
}

function renderMeasurements(rows) {
  measurements = rows;
  const latest = rows.at(-1);
  $('#measurement-count').textContent = `${rows.length} ${rows.length === 1 ? 'medición registrada' : 'mediciones registradas'}`;
  $('#table-count').textContent = `${rows.length} ${rows.length === 1 ? 'registro' : 'registros'}`;
  if (latest) {
    $('#current-temperature').textContent = Number(latest.temperature).toFixed(1);
    $('#current-humidity').textContent = Number(latest.humidity).toFixed(1);
    $('#current-time').textContent = formatDate(latest.recorded_at, { dateStyle: 'short', timeStyle: 'medium' });
  } else {
    $('#current-temperature').textContent = '—';
    $('#current-humidity').textContent = '—';
    $('#current-time').textContent = 'Sin datos';
  }

  const body = $('#measurement-rows');
  body.replaceChildren();
  if (!rows.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 4;
    cell.className = 'empty-row';
    cell.textContent = 'Esperando la primera lectura del sensor…';
  } else {
    [...rows].reverse().slice(0, 12).forEach((item) => {
      const row = body.insertRow();
      const values = [
        formatDate(item.recorded_at),
        `${Number(item.temperature).toFixed(1)} °C`,
        `${Number(item.humidity).toFixed(1)} %`,
      ];
      values.forEach((value, index) => {
        const cell = row.insertCell();
        cell.textContent = value;
        if (index > 0) cell.className = 'value-cell';
      });
      const state = row.insertCell();
      const badge = document.createElement('span');
      badge.className = 'state-pill';
      badge.textContent = 'Registrada';
      state.append(badge);
    });
  }
  drawChart(rows);
}

function drawChart(rows) {
  const context = chart.getContext('2d');
  const bounds = chart.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  chart.width = Math.max(1, Math.floor(bounds.width * ratio));
  chart.height = Math.max(1, Math.floor(bounds.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = bounds.width;
  const height = bounds.height;
  context.clearRect(0, 0, width, height);
  $('#chart-empty').style.display = rows.length ? 'none' : 'flex';
  if (!rows.length) return;

  const padding = { top: 10, right: 38, bottom: 30, left: 38 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const series = [
    { key: 'temperature', color: '#ee906c', side: 'left', unit: '°C' },
    { key: 'humidity', color: '#7795c2', side: 'right', unit: '%' },
  ];
  const ranges = Object.fromEntries(series.map(({ key }) => {
    const values = rows.map((row) => Number(row[key]));
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = Math.max(high - low, 1);
    return [key, { min: low - span * 0.12, max: high + span * 0.12 }];
  }));
  const x = (index) => padding.left + (rows.length === 1 ? plotWidth / 2 : index * plotWidth / (rows.length - 1));
  const y = (value, key) => {
    const range = ranges[key];
    return padding.top + (range.max - value) * plotHeight / (range.max - range.min);
  };

  context.font = '10px DM Sans, sans-serif';
  context.textBaseline = 'middle';
  for (let tick = 0; tick <= 4; tick += 1) {
    const yy = padding.top + tick * plotHeight / 4;
    const temperatureRange = ranges.temperature;
    const humidityRange = ranges.humidity;
    const temperatureLabel = temperatureRange.max - tick * (temperatureRange.max - temperatureRange.min) / 4;
    const humidityLabel = humidityRange.max - tick * (humidityRange.max - humidityRange.min) / 4;
    context.beginPath();
    context.strokeStyle = '#edf1ef';
    context.lineWidth = 1;
    context.moveTo(padding.left, yy);
    context.lineTo(width - padding.right, yy);
    context.stroke();
    context.fillStyle = '#98a39e';
    context.textAlign = 'right';
    context.fillText(temperatureLabel.toFixed(1), padding.left - 9, yy);
    context.textAlign = 'left';
    context.fillText(humidityLabel.toFixed(0), width - padding.right + 4, yy);
  }
  series.forEach(({ key, color }) => {
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.lineJoin = 'round';
    context.lineCap = 'round';
    rows.forEach((row, index) => {
      const px = x(index);
      const py = y(Number(row[key]), key);
      if (index === 0) context.moveTo(px, py);
      else context.lineTo(px, py);
    });
    context.stroke();
    if (rows.length === 1) {
      context.beginPath();
      context.arc(x(0), y(Number(rows[0][key]), key), 3.5, 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
    }
  });
  context.fillStyle = '#98a39e';
  context.textAlign = 'left';
  context.textBaseline = 'alphabetic';
  context.fillText(formatDate(rows[0].recorded_at, { dateStyle: 'short', timeStyle: 'short' }), padding.left, height - 7);
  const lastLabel = formatDate(rows.at(-1).recorded_at, { dateStyle: 'short', timeStyle: 'short' });
  context.textAlign = 'right';
  context.fillText(lastLabel, width - padding.right, height - 7);
}

async function refreshMeasurements() {
  try {
    const response = await fetch('/api/measurements?limit=500', { cache: 'no-store' });
    if (!response.ok) throw new Error('No se pudieron cargar las mediciones');
    renderMeasurements(await response.json());
  } catch (error) {
    console.error(error);
  }
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    const { serial } = await response.json();
    $('#status-text').textContent = serial.message;
    $('#status-dot').className = `status-dot ${serial.connected ? 'connected' : 'disconnected'}`;
  } catch {
    $('#status-text').textContent = 'Servidor no disponible';
    $('#status-dot').className = 'status-dot disconnected';
  }
}

refreshMeasurements();
refreshStatus();
window.setInterval(refreshMeasurements, 5000);
window.setInterval(refreshStatus, 5000);
window.addEventListener('resize', () => drawChart(measurements));
