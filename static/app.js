// Глобальные переменные состояния
let videoMetadata = null;
let eventSource = null;
let currentTaskId = null;

// Элементы DOM
const urlInput = document.getElementById('video-url');
const btnAnalyze = document.getElementById('btn-analyze');
const btnAnalyzeText = btnAnalyze.querySelector('.btn-text');
const btnAnalyzeSpinner = btnAnalyze.querySelector('.spinner');
const btnAnalyzeIcon = btnAnalyze.querySelector('.btn-icon');
const urlError = document.getElementById('url-error');

// Секции
const urlSection = document.getElementById('url-section');
const detailsSection = document.getElementById('details-section');
const progressSection = document.getElementById('progress-section');
const successSection = document.getElementById('success-section');

// Детали видео
const videoThumbnail = document.getElementById('video-thumbnail');
const videoTitle = document.getElementById('video-title');
const videoAuthor = document.getElementById('video-author');
const videoDuration = document.getElementById('video-duration');
const formatSelect = document.getElementById('format-select');

// Обрезка видео
const cropToggle = document.getElementById('crop-toggle');
const cropInputs = document.getElementById('crop-inputs');
const cropStart = document.getElementById('crop-start');
const cropEnd = document.getElementById('crop-end');

// Скачивание и прогресс
const btnDownload = document.getElementById('btn-download');
const btnCancel = document.getElementById('btn-cancel');
const statusTitle = document.getElementById('status-title');
const statusSpinner = document.getElementById('status-spinner');
const progressBarFill = document.getElementById('progress-bar-fill');
const progressPercent = document.getElementById('progress-percent');
const downloadSpeed = document.getElementById('download-speed');
const downloadEta = document.getElementById('download-eta');
const statusMsg = document.getElementById('status-msg');

// Завершение скачивания
const btnFetchFile = document.getElementById('btn-fetch-file');
const btnReset = document.getElementById('btn-reset');

// Установка слушателей событий
btnAnalyze.addEventListener('click', analyzeVideo);
cropToggle.addEventListener('change', toggleCropInputs);
btnDownload.addEventListener('click', startDownload);
btnCancel.addEventListener('click', cancelDownload);
btnReset.addEventListener('click', resetApp);

// Функция для форматирования секунд в HH:MM:SS
function secondsToTimecode(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return [h, m, s].map(v => v < 10 ? '0' + v : v).join(':');
}

// Функция для парсинга таймкода в секунды
function timecodeToSeconds(timecode) {
    const parts = timecode.trim().split(':').map(Number);
    if (parts.some(isNaN)) return NaN;
    if (parts.length === 1) return parts[0];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return NaN;
}

// Функция анализа видео
async function analyzeVideo() {
    const url = urlInput.value.trim();
    if (!url) {
        showUrlError("Пожалуйста, введите ссылку на видеоролик.");
        return;
    }

    // Показываем загрузку на кнопке
    btnAnalyze.disabled = true;
    btnAnalyzeText.textContent = "Анализ...";
    btnAnalyzeIcon.classList.add('hidden');
    btnAnalyzeSpinner.classList.remove('hidden');
    urlError.classList.add('hidden');
    detailsSection.classList.add('hidden');

    try {
        const response = await fetch('/api/downloader/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Не удалось проанализировать видеоролик.");
        }

        // Заполняем информацию о видео
        videoMetadata = data;
        videoThumbnail.src = data.thumbnail || 'https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=300';
        videoTitle.textContent = data.title;
        videoAuthor.innerHTML = `<i class="fa-solid fa-circle-user icon-sm"></i> ${data.author || 'YouTube Channel'}`;
        videoDuration.innerHTML = `<i class="fa-regular fa-clock icon-sm"></i> ${data.duration_formatted}`;

        // Заполняем выпадающий список разрешений
        formatSelect.innerHTML = '';
        data.formats.forEach(f => {
            const option = document.createElement('option');
            option.value = f.resolution; // Передаем "1080p", "720p", "audio" и т.д.
            
            let sizeText = f.filesize_mb ? ` (~${f.filesize_mb} MB)` : '';
            let fpsText = f.fps ? ` [${f.fps} FPS]` : '';
            let noteText = f.note ? ` - ${f.note}` : '';
            
            if (f.resolution === 'audio') {
                option.textContent = `Только Аудио (MP3 high quality)`;
            } else {
                option.textContent = `Видео: ${f.resolution}${fpsText}${sizeText}${noteText}`;
            }
            formatSelect.appendChild(option);
        });

        // Настройка значений по умолчанию для обрезки
        cropStart.value = "00:00:00";
        cropEnd.value = data.duration_formatted;

        // Показываем блок с настройками
        detailsSection.classList.remove('hidden');
        // Скроллим к деталям видео для мобилок
        detailsSection.scrollIntoView({ behavior: 'smooth' });

    } catch (err) {
        showUrlError(err.message);
    } finally {
        // Возвращаем кнопку в исходное состояние
        btnAnalyze.disabled = false;
        btnAnalyzeText.textContent = "Анализировать";
        btnAnalyzeIcon.classList.remove('hidden');
        btnAnalyzeSpinner.classList.add('hidden');
    }
}

function showUrlError(message) {
    urlError.querySelector('.error-text').textContent = message;
    urlError.classList.remove('hidden');
}

// Функция для управления полями обрезки
function toggleCropInputs() {
    if (cropToggle.checked) {
        cropInputs.classList.remove('hidden-height');
        cropInputs.classList.add('visible-height');
    } else {
        cropInputs.classList.remove('visible-height');
        cropInputs.classList.add('hidden-height');
    }
}

// Запуск скачивания
async function startDownload() {
    if (!videoMetadata) return;

    const resolution = formatSelect.value;
    const needCrop = cropToggle.checked;
    let startVal = cropStart.value.trim();
    let endVal = cropEnd.value.trim();

    if (needCrop) {
        // Валидация таймкодов
        const startSec = timecodeToSeconds(startVal);
        const endSec = timecodeToSeconds(endVal);

        if (isNaN(startSec) || isNaN(endSec)) {
            alert("Пожалуйста, введите корректные таймкоды начала и конца (например: 00:01:30 или 90).");
            return;
        }
        if (startSec >= endSec) {
            alert("Время начала фрагмента должно быть меньше времени конца.");
            return;
        }
        if (endSec > videoMetadata.duration) {
            alert("Таймкод конца обрезки превышает общую длительность видео.");
            return;
        }
        
        const cropDuration = endSec - startSec;
        if (cropDuration > 3600) {
            alert("Максимальная длительность обрезаемого фрагмента — 1 час (3600 сек).");
            return;
        }
        
        // Преобразуем к стандартному виду HH:MM:SS для надежности бэкенда
        startVal = secondsToTimecode(startSec);
        endVal = secondsToTimecode(endSec);
    }

    try {
        btnDownload.disabled = true;
        
        const response = await fetch('/api/downloader/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: urlInput.value.trim(),
                resolution: resolution,
                title: videoMetadata.title,
                need_crop: needCrop,
                crop_start: needCrop ? startVal : null,
                crop_end: needCrop ? endVal : null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Не удалось поставить задачу на скачивание.");
        }

        currentTaskId = data.task_id;
        
        // Переключаем интерфейс на экран прогресса
        detailsSection.classList.add('hidden');
        progressSection.classList.remove('hidden');
        
        // Сбрасываем прогресс-бар
        progressBarFill.style.width = '0%';
        progressPercent.textContent = '0%';
        downloadSpeed.textContent = '0.0 MiB/s';
        downloadEta.innerHTML = `<i class="fa-regular fa-hourglass icon-sm"></i> Осталось: --:--`;
        statusTitle.textContent = "Подготовка к скачиванию...";
        statusMsg.textContent = "Подключение к YouTube DASH потокам...";
        statusSpinner.classList.remove('hidden');

        // Запускаем SSE мониторинг прогресса
        monitorProgress(currentTaskId);

    } catch (err) {
        alert("Ошибка: " + err.message);
        btnDownload.disabled = false;
    }
}

// Мониторинг прогресса через Server-Sent Events
function monitorProgress(taskId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/downloader/tasks/${taskId}/progress`);

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        // Обработка ошибок в SSE
        if (data.error) {
            handleDownloadError(data.error);
            return;
        }

        // Обновление статуса
        if (data.status === 'downloading') {
            statusTitle.textContent = "Скачивание видео...";
            progressBarFill.style.width = `${data.progress}%`;
            progressPercent.textContent = `${data.progress}%`;
            downloadSpeed.textContent = data.speed || '0.0 MiB/s';
            downloadEta.innerHTML = `<i class="fa-regular fa-hourglass icon-sm"></i> Осталось: ${data.eta || '--:--'}`;
            statusMsg.textContent = "Загрузка фрагментов DASH-потоков...";
        } 
        
        else if (data.status === 'processing') {
            statusTitle.textContent = "Обработка видео...";
            progressBarFill.style.width = '95%';
            progressPercent.textContent = '95%';
            downloadSpeed.textContent = 'N/A';
            downloadEta.innerHTML = `<i class="fa-regular fa-hourglass icon-sm"></i> Обработка...`;
            statusMsg.textContent = data.eta || "Слияние аудио и видео дорожек через ffmpeg...";
        } 
        
        else if (data.status === 'completed') {
            eventSource.close();
            eventSource = null;
            
            // Переключаем интерфейс на успех
            progressSection.classList.add('hidden');
            successSection.classList.remove('hidden');
            
            // Настраиваем ссылку скачивания
            const downloadUrl = `/api/downloader/files/${taskId}`;
            btnFetchFile.href = downloadUrl;
            
            // Автоматическое скачивание
            window.location.href = downloadUrl;
        } 
        
        else if (data.status === 'failed') {
            handleDownloadError(data.error || "Скачивание прервано сервером.");
        }
    };

    eventSource.onerror = function() {
        console.error("SSE Connection Error. Переподключение...");
        // В случае разрыва SSE браузер автоматически переподключится,
        // но мы выведем сообщение, чтобы пользователь не волновался.
        statusMsg.textContent = "Соединение с сервером временно потеряно. Попытка восстановить связь...";
    };
}

// Обработка ошибок загрузки
function handleDownloadError(errorText) {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    alert(`Ошибка скачивания: ${errorText}`);
    
    // Возвращаем форму настроек
    progressSection.classList.add('hidden');
    detailsSection.classList.remove('hidden');
    btnDownload.disabled = false;
}

// Отмена скачивания
function cancelDownload() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    progressSection.classList.add('hidden');
    detailsSection.classList.remove('hidden');
    btnDownload.disabled = false;
}

// Сброс приложения для нового скачивания
function resetApp() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    currentTaskId = null;
    videoMetadata = null;
    
    urlInput.value = '';
    cropToggle.checked = false;
    toggleCropInputs();
    
    successSection.classList.add('hidden');
    detailsSection.classList.add('hidden');
    progressSection.classList.add('hidden');
    urlError.classList.add('hidden');
    
    btnDownload.disabled = false;
    urlSection.scrollIntoView({ behavior: 'smooth' });
}

// Инициализация интерфейса и фона при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    initDotField();
});

function initThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;

    // Считываем сохраненную тему из localStorage или системных настроек
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
        document.body.classList.add('dark-mode');
    }

    btn.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        const isDark = document.body.classList.contains('dark-mode');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });
}

function initDotField() {
    const canvas = document.getElementById('dot-field-canvas');
    const glowEl = document.getElementById('dot-field-glow');
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    let dots = [];
    const mouse = { x: -9999, y: -9999, prevX: -9999, prevY: -9999, speed: 0 };
    let size = { w: 0, h: 0, offsetX: 0, offsetY: 0 };
    let glowOpacity = 0;
    let engagement = 0;
    let frameCount = 0;
    let rafId = null;
    let resizeTimer;

    const config = {
        dotRadius: 1.5,
        dotSpacing: 14,
        cursorRadius: 500,
        cursorForce: 0.1,
        bulgeOnly: true,
        bulgeStrength: 67,
        glowRadius: 160,
        sparkle: false,
        waveAmplitude: 0,
        gradientFrom: 'rgba(230, 0, 35, 0.12)', // Pinterest Red (подсветка)
        gradientTo: 'rgba(0, 0, 0, 0.05)'      // Серый нейтральный тон
    };

    function resize() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(doResize, 100);
    }

    function doResize() {
        const rect = canvas.parentElement.getBoundingClientRect();
        const w = rect.width;
        const h = rect.height;

        canvas.width = w * dpr;
        canvas.height = h * dpr;
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        size = {
            w,
            h,
            offsetX: rect.left + window.scrollX,
            offsetY: rect.top + window.scrollY,
        };

        buildDots(w, h);
    }

    function buildDots(w, h) {
        const step = config.dotRadius + config.dotSpacing;
        const cols = Math.floor(w / step);
        const rows = Math.floor(h / step);
        const padX = (w % step) / 2;
        const padY = (h % step) / 2;
        dots = new Array(rows * cols);
        let idx = 0;

        for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
                const ax = padX + col * step + step / 2;
                const ay = padY + row * step + step / 2;
                dots[idx++] = { ax, ay, sx: ax, sy: ay, vx: 0, vy: 0, x: ax, y: ay };
            }
        }
    }

    function onMouseMove(e) {
        mouse.x = e.pageX - size.offsetX;
        mouse.y = e.pageY - size.offsetY;
    }

    function updateMouseSpeed() {
        const dx = mouse.prevX - mouse.x;
        const dy = mouse.prevY - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        mouse.speed += (dist - mouse.speed) * 0.5;
        if (mouse.speed < 0.001) mouse.speed = 0;
        mouse.prevX = mouse.x;
        mouse.prevY = mouse.y;
    }

    const speedInterval = setInterval(updateMouseSpeed, 20);

    function tick() {
        frameCount++;
        const { w, h } = size;
        const len = dots.length;
        const t = frameCount * 0.02;

        const targetEngagement = Math.min(mouse.speed / 5, 1);
        engagement += (targetEngagement - engagement) * 0.06;
        if (engagement < 0.001) engagement = 0;

        glowOpacity += (engagement - glowOpacity) * 0.08;

        if (glowEl) {
            glowEl.setAttribute('cx', mouse.x);
            glowEl.setAttribute('cy', mouse.y);
            glowEl.style.opacity = glowOpacity;
        }

        ctx.clearRect(0, 0, w, h);

        // Динамические цвета точек в зависимости от темы
        const isDark = document.body.classList.contains('dark-mode');
        const gradFrom = isDark ? 'rgba(230, 0, 35, 0.22)' : 'rgba(230, 0, 35, 0.12)';
        const gradTo = isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.05)';

        const grad = ctx.createLinearGradient(0, 0, w, h);
        grad.addColorStop(0, gradFrom);
        grad.addColorStop(1, gradTo);
        ctx.fillStyle = grad;

        const cr = config.cursorRadius;
        const crSq = cr * cr;
        const rad = config.dotRadius / 2;
        const isBulge = config.bulgeOnly;

        ctx.beginPath();

        for (let i = 0; i < len; i++) {
            const d = dots[i];
            if (!d) continue;
            const dx = mouse.x - d.ax;
            const dy = mouse.y - d.ay;
            const distSq = dx * dx + dy * dy;

            if (distSq < crSq && engagement > 0.01) {
                const dist = Math.sqrt(distSq);
                if (isBulge) {
                    const tVal = 1 - dist / cr;
                    const push = tVal * tVal * config.bulgeStrength * engagement;
                    const angle = Math.atan2(dy, dx);
                    d.sx += (d.ax - Math.cos(angle) * push - d.sx) * 0.15;
                    d.sy += (d.ay - Math.sin(angle) * push - d.sy) * 0.15;
                } else {
                    const angle = Math.atan2(dy, dx);
                    const move = (500 / dist) * (mouse.speed * config.cursorForce);
                    d.vx += Math.cos(angle) * -move;
                    d.vy += Math.sin(angle) * -move;
                }
            } else if (isBulge) {
                d.sx += (d.ax - d.sx) * 0.1;
                d.sy += (d.ay - d.sy) * 0.1;
            }

            if (!isBulge) {
                d.vx *= 0.9;
                d.vy *= 0.9;
                d.x = d.ax + d.vx;
                d.y = d.ay + d.vy;
                d.sx += (d.x - d.sx) * 0.1;
                d.sy += (d.y - d.sy) * 0.1;
            }

            let drawX = d.sx;
            let drawY = d.sy;
            if (config.waveAmplitude > 0) {
                drawY += Math.sin(d.ax * 0.03 + t) * config.waveAmplitude;
                drawX += Math.cos(d.ay * 0.03 + t * 0.7) * config.waveAmplitude * 0.5;
            }

            if (config.sparkle) {
                const hash = ((i * 2654435761) ^ (frameCount >> 3)) >>> 0;
                if ((hash % 100) < 3) {
                    ctx.moveTo(drawX + rad * 1.8, drawY);
                    ctx.arc(drawX, drawY, rad * 1.8, 0, Math.PI * 2);
                } else {
                    ctx.moveTo(drawX + rad, drawY);
                    ctx.arc(drawX, drawY, rad, 0, Math.PI * 2);
                }
            } else {
                ctx.moveTo(drawX + rad, drawY);
                ctx.arc(drawX, drawY, rad, 0, Math.PI * 2);
            }
        }

        ctx.fill();

        rafId = requestAnimationFrame(tick);
    }

    doResize();
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMouseMove, { passive: true });
    rafId = requestAnimationFrame(tick);
}

