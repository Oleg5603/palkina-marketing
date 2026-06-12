/**
 * Лендинг Светланы Палкиной
 *
 * Что делает этот файл:
 * 1. Читает UTM-параметры из URL и сохраняет в sessionStorage
 * 2. Меняет hero-блок под группу объявления (?g=измена, ?g=развод и т.д.)
 * 3. Подставляет UTM в скрытые поля формы
 * 4. Валидирует и отправляет форму (по умолчанию — через Formspree)
 */

// ---------------------------------------------------------------------------
// 1. Варианты hero под каждую группу объявлений
//    Ключи совпадают со значением URL-параметра ?g=
// ---------------------------------------------------------------------------

const HERO_VARIANTS = {
  специалист: {
    tag:      'Психотерапевт для пар',
    title:    'Психотерапевт для пар — помогу выйти из кризиса',
    subtitle: 'Работаю с парами онлайн. Конфиденциально, без осуждения.',
    pageTitle:'Психотерапевт Светлана Палкина — помощь парам онлайн',
  },
  измена: {
    tag:      'Помощь после измены',
    title:    'Измена разрушила доверие. Это можно пережить.',
    subtitle: 'Помогаю парам справиться с изменой — принять решение и не разрушить себя.',
    pageTitle:'Помощь психотерапевта после измены | Светлана Палкина',
  },
  развод: {
    tag:      'Сохранить брак',
    title:    'На грани развода? Ещё не всё решено.',
    subtitle: 'Помогаю парам найти выход, пока есть возможность сохранить отношения.',
    pageTitle:'Психолог при угрозе развода | Светлана Палкина',
  },
  близость: {
    tag:      'Вернуть близость',
    title:    'Стали чужими? Близость можно вернуть.',
    subtitle: 'Эмоциональное отчуждение — одна из самых болезненных проблем в браке. Я помогаю её решить.',
    pageTitle:'Вернуть близость в браке | Психотерапевт Светлана Палкина',
  },
  конфликты: {
    tag:      'Конфликты в паре',
    title:    'Постоянные ссоры. Круг, из которого есть выход.',
    subtitle: 'Помогаю парам остановить разрушительный цикл конфликтов и снова услышать друг друга.',
    pageTitle:'Постоянные конфликты в паре — помощь психолога | С. Палкина',
  },
  кризис: {
    tag:      'Кризис в браке',
    title:    'Кризис в браке — не приговор.',
    subtitle: 'Многие пары проходят через кризис и выходят из него более близкими. Помогу найти путь.',
    pageTitle:'Кризис в браке — психотерапевт Светлана Палкина',
  },
  доверие: {
    tag:      'Восстановить доверие',
    title:    'Нет доверия. Но восстановить его возможно.',
    subtitle: 'Работаю с парами, где утрачено доверие — шаг за шагом, без давления.',
    pageTitle:'Восстановить доверие в отношениях | Светлана Палкина',
  },
};

// ---------------------------------------------------------------------------
// 2. URL-параметры
// ---------------------------------------------------------------------------

function getUrlParams() {
  const p = new URLSearchParams(window.location.search);
  return {
    g:            p.get('g')            || 'специалист',
    utm_source:   p.get('utm_source')   || '',
    utm_medium:   p.get('utm_medium')   || '',
    utm_campaign: p.get('utm_campaign') || '',
    utm_content:  p.get('utm_content')  || '',
  };
}

function saveUtm(params) {
  // Сохраняем, чтобы UTM не потерялся при навигации по странице
  const keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'g'];
  keys.forEach(k => {
    if (params[k]) sessionStorage.setItem(k, params[k]);
  });
}

function loadUtm() {
  return {
    g:            sessionStorage.getItem('g')            || 'специалист',
    utm_source:   sessionStorage.getItem('utm_source')   || '',
    utm_medium:   sessionStorage.getItem('utm_medium')   || '',
    utm_campaign: sessionStorage.getItem('utm_campaign') || '',
  };
}

// ---------------------------------------------------------------------------
// 3. Применяем hero-вариант
// ---------------------------------------------------------------------------

function applyHeroVariant(group) {
  const variant = HERO_VARIANTS[group] || HERO_VARIANTS['специалист'];

  setText('hero-tag',      variant.tag);
  setText('hero-title',    variant.title);
  setText('hero-subtitle', variant.subtitle);

  const titleEl = document.getElementById('page-title');
  if (titleEl) titleEl.textContent = variant.pageTitle;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ---------------------------------------------------------------------------
// 4. Подставляем UTM в скрытые поля формы
// ---------------------------------------------------------------------------

function fillHiddenFields(params) {
  setVal('utm_source',   params.utm_source);
  setVal('utm_medium',   params.utm_medium);
  setVal('utm_campaign', params.utm_campaign);
  setVal('ad_group',     params.g);
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

// ---------------------------------------------------------------------------
// 5. Форма: валидация и отправка
// ---------------------------------------------------------------------------

function initForm() {
  const form    = document.getElementById('booking-form');
  const success = document.getElementById('form-success');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateForm(form)) return;

    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Отправляю…';

    try {
      await submitForm(form);
      form.hidden = true;
      success.hidden = false;

      const nameInput = document.getElementById('name');
      const nameSpan  = document.getElementById('success-name');
      if (nameInput && nameSpan) {
        nameSpan.textContent = nameInput.value.trim().split(' ')[0];
      }
    } catch {
      btn.disabled = false;
      btn.textContent = 'Записаться';
      showFormError(form, 'Что-то пошло не так. Попробуйте позже или напишите напрямую.');
    }
  });
}

async function submitForm(form) {
  /**
   * По умолчанию — Formspree (бесплатно до 50 заявок/мес).
   * Замените YOUR_FORM_ID на ID из formspree.io после регистрации.
   * Либо замените URL на свой обработчик.
   */
  const FORMSPREE_URL = 'https://formspree.io/f/xpqejgvl';

  const data = new FormData(form);
  const res  = await fetch(FORMSPREE_URL, {
    method: 'POST',
    body:   data,
    headers: { 'Accept': 'application/json' },
  });

  if (!res.ok) throw new Error('submit failed');
}

function validateForm(form) {
  let valid = true;

  const nameField    = form.querySelector('[name="name"]');
  const contactField = form.querySelector('[name="contact"]');

  clearError(nameField);
  clearError(contactField);

  if (!nameField.value.trim()) {
    showError(nameField);
    valid = false;
  }

  const contact = contactField.value.trim();
  if (!contact || (!contact.includes('@') && !/[\d\+]/.test(contact))) {
    showError(contactField);
    valid = false;
  }

  return valid;
}

function showError(input) {
  input.classList.add('error');
  input.closest('.form-field').classList.add('has-error');
}
function clearError(input) {
  input.classList.remove('error');
  input.closest('.form-field').classList.remove('has-error');
}
function showFormError(form, msg) {
  let errEl = form.querySelector('.form-global-error');
  if (!errEl) {
    errEl = document.createElement('p');
    errEl.className = 'form-global-error';
    errEl.style.cssText = 'color:#C04040;font-size:.85rem;text-align:center;margin-top:.5rem';
    form.appendChild(errEl);
  }
  errEl.textContent = msg;
}

// ---------------------------------------------------------------------------
// 6. Calendly — онлайн-запись
//    Шаги: зарегистрируйтесь на calendly.com → скопируйте ссылку вашего
//    расписания → вставьте сюда. Пример: 'https://calendly.com/svetlana-palkina'
//    Если строка пустая — блок скрыт автоматически.
// ---------------------------------------------------------------------------

const CALENDLY_URL = 'https://calendly.com/palkinoleg'; // онлайн-запись

function initCalendly() {
  if (!CALENDLY_URL) return;
  const banner = document.getElementById('calendly-banner');
  const btn    = document.getElementById('calendly-btn');
  if (banner) banner.hidden = false;
  if (btn)    btn.href = CALENDLY_URL;
}

// ---------------------------------------------------------------------------
// 7. Старт
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  const urlParams = getUrlParams();
  saveUtm(urlParams);

  const stored = loadUtm();
  applyHeroVariant(stored.g);
  fillHiddenFields(stored);

  initForm();
  initCalendly();
});
