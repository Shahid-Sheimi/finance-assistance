/**
 * Advanced multi-session chat client.
 * Each user has isolated conversations and persistent memory.
 */
(function () {
    const cfg = window.CHAT_CONFIG;
    const csrf = cfg.csrfToken;

    let activeConversationId = localStorage.getItem('activeConversationId');
    let conversations = [];
    let sending = false;

    const els = {
        list: document.getElementById('conversation-list'),
        messages: document.getElementById('chat-messages'),
        input: document.getElementById('message-input'),
        sendBtn: document.getElementById('send-btn'),
        imageInput: document.getElementById('image-input'),
        csvInput: document.getElementById('csv-input'),
        receiptStatus: document.getElementById('receipt-status'),
        title: document.getElementById('active-chat-title'),
        meta: document.getElementById('active-chat-meta'),
        memory: document.getElementById('memory-content'),
        sidebar: document.getElementById('chat-sidebar'),
    };

    async function api(url, options = {}) {
        const res = await fetch(url, {
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrf,
                ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
                ...options.headers,
            },
            ...options,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Request failed');
        return data;
    }

    function scrollMessages() {
        els.messages.scrollTop = els.messages.scrollHeight;
    }

    function renderWelcome() {
        els.messages.innerHTML = `
            <div class="message assistant">
                <span class="message-label">Assistant</span>
                <div class="message-bubble">Hello! I'm your personal finance assistant.

Each conversation is saved separately. I remember facts you tell me across all chats (see Memory panel).

Try:
• "How much did I spend on groceries?"
• "What subscriptions do I have?"
• "I get paid on the 1st — remember that"

Upload receipts or bank statements with 🖼️. Upload CSV files with 📊.</div>
            </div>`;
    }

    function renderMessages(messages) {
        if (!messages || !messages.length) {
            renderWelcome();
            return;
        }
        els.messages.innerHTML = messages.map(m => `
            <div class="message ${m.role}">
                <span class="message-label">${m.role === 'user' ? 'You' : 'Assistant'}</span>
                <div class="message-bubble"></div>
            </div>
        `).join('');
        els.messages.querySelectorAll('.message').forEach((el, i) => {
            el.querySelector('.message-bubble').textContent = messages[i].content;
        });
        scrollMessages();
    }

    function renderConversationList() {
        if (!conversations.length) {
            els.list.innerHTML = '<div class="memory-empty">No chats yet — click + New</div>';
            return;
        }
        els.list.innerHTML = conversations.map(c => `
            <div class="conversation-item ${c.id === activeConversationId ? 'active' : ''}" data-id="${c.id}">
                <div class="conversation-item-body">
                    <div class="conversation-item-title">${escapeHtml(c.title)}</div>
                    <div class="conversation-item-preview">${escapeHtml(c.preview || 'No messages')}</div>
                    <div class="conversation-item-meta">${c.message_count} msgs</div>
                </div>
                <button type="button" class="btn-delete-conv" data-delete="${c.id}" title="Delete">✕</button>
            </div>
        `).join('');

        els.list.querySelectorAll('.conversation-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.closest('[data-delete]')) return;
                loadConversation(item.dataset.id);
            });
        });
        els.list.querySelectorAll('[data-delete]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteConversation(btn.dataset.delete);
            });
        });
    }

    function escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = text || '';
        return d.innerHTML;
    }

    function updateTitleBar(conv) {
        if (!conv) {
            els.title.textContent = 'Finance Assistant';
            els.meta.textContent = 'Select or start a conversation';
            return;
        }
        els.title.textContent = conv.title || 'New Chat';
        els.meta.textContent = conv.context_summary || `${conv.message_count || 0} messages`;
    }

    async function loadConversations() {
        const data = await api(cfg.urls.conversations);
        conversations = data.conversations || [];
        renderConversationList();

        if (activeConversationId && conversations.find(c => c.id === activeConversationId)) {
            await loadConversation(activeConversationId, false);
        } else if (conversations.length) {
            await loadConversation(conversations[0].id, false);
        } else {
            await createConversation();
        }
    }

    async function loadConversation(id, refreshList = true) {
        activeConversationId = id;
        localStorage.setItem('activeConversationId', id);
        const data = await api(cfg.urls.conversationDetail + id + '/');
        renderMessages(data.messages);
        updateTitleBar(data);
        if (refreshList) {
            const idx = conversations.findIndex(c => c.id === id);
            if (idx >= 0) Object.assign(conversations[idx], data);
            renderConversationList();
        }
        els.sidebar.classList.remove('open');
    }

    async function createConversation() {
        const data = await api(cfg.urls.conversationNew, { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) });
        conversations.unshift(data);
        activeConversationId = data.id;
        localStorage.setItem('activeConversationId', data.id);
        renderConversationList();
        renderWelcome();
        updateTitleBar(data);
    }

    async function deleteConversation(id) {
        if (!confirm('Delete this conversation and all its messages?')) return;
        const data = await api(cfg.urls.conversationDelete + id + '/delete/', { method: 'POST' });
        conversations = conversations.filter(c => c.id !== id);
        if (data.active_conversation) {
            activeConversationId = data.active_conversation.id;
            localStorage.setItem('activeConversationId', activeConversationId);
            conversations.unshift(data.active_conversation);
            await loadConversation(activeConversationId);
        }
        renderConversationList();
        await loadMemory();
    }

    async function renameConversation() {
        if (!activeConversationId) return;
        const title = prompt('Rename conversation:', els.title.textContent);
        if (!title || !title.trim()) return;
        const data = await api(cfg.urls.conversationRename + activeConversationId + '/rename/', {
            method: 'POST',
            body: JSON.stringify({ title: title.trim() }),
        });
        updateTitleBar(data);
        const idx = conversations.findIndex(c => c.id === activeConversationId);
        if (idx >= 0) conversations[idx] = data;
        renderConversationList();
    }

    function appendMessage(role, content) {
        const wrap = document.createElement('div');
        wrap.className = 'message ' + role;
        wrap.innerHTML = `<span class="message-label">${role === 'user' ? 'You' : 'Assistant'}</span><div class="message-bubble"></div>`;
        wrap.querySelector('.message-bubble').textContent = content;
        els.messages.appendChild(wrap);
        scrollMessages();
    }

    function showTyping() {
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.id = 'typing';
        el.innerHTML = '<span class="message-label">Assistant</span><div class="typing-indicator"><span></span><span></span><span></span></div>';
        els.messages.appendChild(el);
        scrollMessages();
    }

    function hideTyping() {
        document.getElementById('typing')?.remove();
    }

    async function sendMessage(text) {
        text = (text || els.input.value).trim();
        if (!text || sending || !activeConversationId) return;
        sending = true;
        els.sendBtn.disabled = true;
        els.input.value = '';
        appendMessage('user', text);
        showTyping();

        try {
            const data = await api(cfg.urls.send, {
                method: 'POST',
                body: JSON.stringify({ message: text, conversation_id: activeConversationId }),
            });
            hideTyping();
            appendMessage('assistant', data.content);
            if (data.conversation) {
                updateTitleBar(data.conversation);
                const idx = conversations.findIndex(c => c.id === activeConversationId);
                if (idx >= 0) conversations[idx] = data.conversation;
                else conversations.unshift(data.conversation);
                renderConversationList();
            }
            await loadMemory();
        } catch (e) {
            hideTyping();
            appendMessage('assistant', 'Error: ' + e.message);
        }

        sending = false;
        els.sendBtn.disabled = false;
        els.input.focus();
    }

    async function uploadImage(file) {
        if (!file || !activeConversationId) return;
        els.receiptStatus.textContent = 'Processing image…';
        appendMessage('user', '[Uploaded image: ' + file.name + ']');
        showTyping();

        const form = new FormData();
        form.append('receipt_image', file);
        form.append('conversation_id', activeConversationId);

        try {
            const data = await api(cfg.urls.upload, { method: 'POST', body: form });
            hideTyping();
            appendMessage('assistant', data.content);
            if (data.conversation) updateTitleBar(data.conversation);
            els.receiptStatus.textContent = 'Receipt or bank statement · each chat is saved separately';
        } catch (e) {
            hideTyping();
            appendMessage('assistant', 'Upload failed: ' + e.message);
            els.receiptStatus.textContent = '';
        }
        if (els.imageInput) els.imageInput.value = '';
    }

    async function uploadDocument(file) {
        if (!file || !activeConversationId) return;
        els.receiptStatus.textContent = 'Processing document…';
        appendMessage('user', '[Uploaded document: ' + file.name + ']');
        showTyping();

        const form = new FormData();
        form.append('document', file);
        form.append('conversation_id', activeConversationId);

        try {
            const data = await api(cfg.urls.uploadDocument, { method: 'POST', body: form });
            hideTyping();
            appendMessage('assistant', data.content);
            if (data.conversation) updateTitleBar(data.conversation);
            els.receiptStatus.textContent = 'CSV or document · each chat is saved separately';
        } catch (e) {
            hideTyping();
            appendMessage('assistant', 'Document processing failed: ' + e.message);
            els.receiptStatus.textContent = '';
        }
        if (els.csvInput) els.csvInput.value = '';
    }

    async function loadMemory() {
        try {
            const data = await api(cfg.urls.memory);
            renderMemory(data);
        } catch (e) {
            els.memory.innerHTML = '<div class="memory-empty">Could not load memory.</div>';
        }
    }

    function renderMemory(data) {
        const sections = [
            ['Facts', data.facts],
            ['Rules', data.rules],
            ['Goals', data.goals],
            ['Preferences', data.preferences],
        ];
        let html = '';
        for (const [label, items] of sections) {
            html += `<div class="memory-section"><h3>${label}</h3>`;
            if (!items || !items.length) {
                html += '<div class="memory-empty">None saved yet</div>';
            } else {
                html += items.map(item => `
                    <div class="memory-item">
                        <div>
                            <div class="memory-item-value">${escapeHtml(item.value)}</div>
                            <div class="memory-item-key">${escapeHtml(item.key)}</div>
                        </div>
                        <button type="button" class="btn-delete-conv" data-memory-delete="${item.id}" title="Forget">✕</button>
                    </div>
                `).join('');
            }
            html += '</div>';
        }
        els.memory.innerHTML = html || '<div class="memory-empty">Tell me things like "I get paid on the 1st" to build memory.</div>';

        els.memory.querySelectorAll('[data-memory-delete]').forEach(btn => {
            btn.addEventListener('click', async () => {
                await api(cfg.urls.memoryDelete + btn.dataset.memoryDelete + '/delete/', { method: 'POST' });
                loadMemory();
            });
        });
    }

    async function importData() {
        const btn = document.getElementById('import-btn');
        btn.disabled = true;
        btn.textContent = 'Importing…';
        try {
            const data = await api(cfg.urls.importData, {
                method: 'POST',
                body: JSON.stringify({ source: 'api' }),
            });
            appendMessage('assistant', data.message || 'Sample data loaded.');
        } catch (e) {
            appendMessage('assistant', e.message || 'Import failed.');
        }
        btn.disabled = false;
        btn.textContent = 'Import sample data';
    }

    // Event listeners
    document.getElementById('new-chat-btn').addEventListener('click', createConversation);
    document.getElementById('delete-chat-btn').addEventListener('click', () => {
        if (activeConversationId) deleteConversation(activeConversationId);
    });
    document.getElementById('rename-chat-btn').addEventListener('click', renameConversation);
    document.getElementById('import-btn').addEventListener('click', importData);
    document.getElementById('import-btn-sidebar')?.addEventListener('click', importData);
    document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
        els.sidebar.classList.toggle('open');
    });
    els.sendBtn.addEventListener('click', () => sendMessage());
    els.input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    if (els.imageInput) {
        els.imageInput.addEventListener('change', () => {
            if (els.imageInput.files[0]) uploadImage(els.imageInput.files[0]);
        });
    }
    if (els.csvInput) {
        els.csvInput.addEventListener('change', () => {
            if (els.csvInput.files[0]) uploadDocument(els.csvInput.files[0]);
        });
    }
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => sendMessage(chip.dataset.prompt));
    });

    // Init
    loadConversations().then(loadMemory).catch(err => {
        els.list.innerHTML = '<div class="memory-empty">Failed to load. Refresh the page.</div>';
        console.error(err);
    });
    els.input.focus();
})();
