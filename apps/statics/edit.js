/* =========================================================
 * Edit mode for the static promo screens.
 *
 * Open a static with ?edit on the end of the URL, e.g.
 *   openDay.html?edit
 * and every piece of text becomes click-to-type. Save writes
 * the HTML back out; render.bat then makes the PNG.
 *
 * Does nothing without ?edit, so render.bat is unaffected.
 * ========================================================= */
(function () {
    if (!/(^|[?&])edit\b/.test(location.search)) return;

    var EDITABLE = [
        '.event', '.datebar', '.standfirst', '.column-head',
        '.slot .time', '.slot .who', '.slot .note', '.slot .where',
        '.chip .label', '.chip .sub',
        '.notes span', '.footer .cta', '.footer .url'
    ].join(', ');

    var dirty = false;

    /* Edit-only chrome, injected so statics.css stays render-clean */
    var css = document.createElement('style');
    css.id = 'edit-only';
    css.textContent = [
        '[contenteditable]:hover { outline: 2px dashed rgba(255,102,0,0.55); outline-offset: 3px; }',
        '[contenteditable]:focus { outline: 2px solid #ff6600; outline-offset: 3px; background: rgba(255,102,0,0.10); }',
        '.slot { position: relative; }',
        '.ed-row { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; opacity: 0; transition: opacity .12s; }',
        '.slot:hover .ed-row { opacity: 1; }',
        '.ed-row button { width: 26px; height: 26px; border: 0; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.16); color: #fff; font: 700 14px/1 Inter, sans-serif; }',
        '.ed-row button:hover { background: #ff6600; }',
        '.ed-add { display: block; width: 100%; margin-top: 14px; padding: 9px; cursor: pointer; border: 2px dashed rgba(255,255,255,0.28); border-radius: 6px; background: transparent; color: rgba(255,255,255,0.75); font: 800 16px/1 Inter, sans-serif; letter-spacing: 2px; text-transform: uppercase; }',
        '.ed-add:hover { border-color: #ff6600; color: #ff6600; }',
        '#ed-bar { position: fixed; right: 20px; top: 20px; z-index: 9999; display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 10px; background: rgba(6,10,40,0.94); border: 1px solid rgba(255,255,255,0.16); box-shadow: 0 10px 40px rgba(0,0,0,0.55); font: 600 15px/1 Inter, sans-serif; color: #fff; }',
        '#ed-bar button { padding: 10px 16px; border: 0; border-radius: 6px; cursor: pointer; background: #ff6600; color: #fff; font: 800 15px/1 Inter, sans-serif; }',
        '#ed-bar button.ghost { background: rgba(255,255,255,0.14); }',
        '#ed-bar button:hover { filter: brightness(1.12); }',
        '#ed-bar .hint { color: rgba(255,255,255,0.6); font-weight: 500; }',
        '#ed-bar .dot { width: 8px; height: 8px; border-radius: 50%; background: #3ddc84; }',
        '#ed-bar.dirty .dot { background: #ff6600; }'
    ].join('\n');
    document.head.appendChild(css);

    function touch() {
        dirty = true;
        bar.classList.add('dirty');
    }

    /* Make text click-to-type */
    function arm(el) {
        el.setAttribute('contenteditable', 'true');
        el.setAttribute('spellcheck', 'false');
        el.addEventListener('input', touch);
        // Enter would inject <div>/<br> into the saved HTML; let text wrap instead
        el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') e.preventDefault();
        });
        // Keep pasted text plain so Word/Canva styling cannot leak in
        el.addEventListener('paste', function (e) {
            e.preventDefault();
            var text = (e.clipboardData || window.clipboardData).getData('text/plain');
            document.execCommand('insertText', false, text.replace(/\s*\n\s*/g, ' '));
        });
    }
    document.querySelectorAll(EDITABLE).forEach(arm);

    /* Per-row controls: delete, and toggle the MATCH highlight */
    function addRowControls(slot) {
        if (slot.querySelector('.ed-row')) return;
        var box = document.createElement('div');
        box.className = 'ed-row';

        if (!slot.closest('.schedule.single')) {
            var star = document.createElement('button');
            star.type = 'button';
            star.textContent = '★';
            star.title = 'Highlight as a match';
            star.addEventListener('click', function () {
                slot.classList.toggle('match');
                var tag = slot.querySelector('.tag');
                if (slot.classList.contains('match') && !tag) {
                    tag = document.createElement('div');
                    tag.className = 'tag';
                    tag.textContent = 'Match';
                    arm(tag);
                    slot.appendChild(tag);
                } else if (!slot.classList.contains('match') && tag) {
                    tag.remove();
                }
                touch();
            });
            box.appendChild(star);
        }

        var del = document.createElement('button');
        del.type = 'button';
        del.textContent = '×';
        del.title = 'Delete this row';
        del.addEventListener('click', function () {
            slot.remove();
            touch();
        });
        box.appendChild(del);

        slot.appendChild(box);
    }
    document.querySelectorAll('.slot').forEach(addRowControls);

    /* Add a row to each column */
    document.querySelectorAll('.slots').forEach(function (slots) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ed-add';
        btn.textContent = '+ Add session';
        btn.addEventListener('click', function () {
            var last = slots.querySelector('.slot:last-of-type');
            if (!last) return;
            var copy = last.cloneNode(true);
            copy.classList.remove('match');
            var tag = copy.querySelector('.tag');
            if (tag) tag.remove();
            var ctl = copy.querySelector('.ed-row');
            if (ctl) ctl.remove();
            copy.querySelectorAll('.time, .who, .note, .where').forEach(function (n) {
                n.textContent = n.classList.contains('time') ? '00.00 – 00.00' : 'New entry';
            });
            slots.appendChild(copy);
            copy.querySelectorAll(EDITABLE).forEach(arm);
            addRowControls(copy);
            touch();
        });
        slots.parentNode.appendChild(btn);
    });

    /* Serialise back to clean HTML */
    function cleanHTML() {
        var doc = document.documentElement.cloneNode(true);
        doc.querySelectorAll('#edit-only, #ed-bar, .ed-row, .ed-add').forEach(function (n) {
            n.remove();
        });
        doc.querySelectorAll('[contenteditable]').forEach(function (n) {
            n.removeAttribute('contenteditable');
            n.removeAttribute('spellcheck');
        });
        return '<!DOCTYPE html>\n' + doc.outerHTML + '\n';
    }

    function filename() {
        return decodeURIComponent(location.pathname.split('/').pop()) || 'static.html';
    }

    var handle = null;
    async function save() {
        var html = cleanHTML();
        try {
            if (!window.showSaveFilePicker) throw new Error('no picker');
            if (!handle) {
                handle = await window.showSaveFilePicker({
                    suggestedName: filename(),
                    types: [{ description: 'HTML', accept: { 'text/html': ['.html'] } }]
                });
            }
            var w = await handle.createWritable();
            await w.write(html);
            await w.close();
        } catch (err) {
            if (err && err.name === 'AbortError') return;
            // Fallback: download it, then copy the file back over the original
            var a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
            a.download = filename();
            a.click();
            URL.revokeObjectURL(a.href);
        }
        dirty = false;
        bar.classList.remove('dirty');
        status.textContent = 'Saved — now run render.bat';
        setTimeout(function () {
            status.textContent = 'Click any text to edit';
        }, 4000);
    }

    /* Toolbar */
    var bar = document.createElement('div');
    bar.id = 'ed-bar';

    var dot = document.createElement('span');
    dot.className = 'dot';

    var status = document.createElement('span');
    status.className = 'hint';
    status.textContent = 'Click any text to edit';

    var previewBtn = document.createElement('button');
    previewBtn.type = 'button';
    previewBtn.className = 'ghost';
    previewBtn.textContent = 'Preview';
    previewBtn.addEventListener('click', function () {
        if (dirty && !confirm('You have unsaved changes. Leave edit mode anyway?')) return;
        dirty = false;
        location.search = '';
    });

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', save);

    bar.appendChild(dot);
    bar.appendChild(status);
    bar.appendChild(previewBtn);
    bar.appendChild(saveBtn);
    document.body.appendChild(bar);

    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            save();
        }
    });

    window.addEventListener('beforeunload', function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
})();
