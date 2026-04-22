/**
 * Waggy AI Chatbot Logic
 */

let isChatOpen = false;
let chatHistory = [];

function toggleChat() {
    const widget = document.getElementById('aiChatWidget');
    isChatOpen = !isChatOpen;
    
    if (isChatOpen) {
        widget.style.display = 'block';
        document.getElementById('aiMessageInput').focus();
    } else {
        widget.style.display = 'none';
    }
}

function appendMessage(role, content) {
    const chatArea = document.getElementById('chatArea');
    const indicator = document.getElementById('typingIndicator');
    
    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${role === 'user' ? 'msg-user' : 'msg-ai'} pb-1`;
    
    // Parse very basic markdown-lite for links and bold
    let formattedContent = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
        
    bubble.innerHTML = formattedContent;
    
    // Insert before typing indicator
    chatArea.insertBefore(bubble, indicator);
    
    // Scroll to bottom
    chatArea.scrollTop = chatArea.scrollHeight;
}

function showTyping() {
    const indicator = document.getElementById('typingIndicator');
    const chatArea = document.getElementById('chatArea');
    indicator.style.display = 'flex';
    chatArea.scrollTop = chatArea.scrollHeight;
}

function hideTyping() {
    const indicator = document.getElementById('typingIndicator');
    indicator.style.display = 'none';
}

async function handleSend(e) {
    e.preventDefault();
    
    const input = document.getElementById('aiMessageInput');
    const message = input.value.trim();
    const btn = document.getElementById('aiSendBtn');
    
    if (!message) return;
    
    // Disable input while processing
    input.value = '';
    input.disabled = true;
    btn.disabled = true;
    
    // Add User Message
    appendMessage('user', message);
    
    // Add to History
    chatHistory.push({"role": "user", "content": message});
    
    // Keep history length manageable
    if (chatHistory.length > 10) {
        chatHistory = chatHistory.slice(chatHistory.length - 10);
    }
    
    showTyping();
    
    try {
        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                history: chatHistory.slice(0, -1) // send previous history
            })
        });
        
        const data = await response.json();
        
        hideTyping();
        input.disabled = false;
        btn.disabled = false;
        input.focus();
        
        if (data.success) {
            appendMessage('ai', data.message);
            chatHistory.push({"role": "assistant", "content": data.message});
        } else {
            appendMessage('ai', 'Oops! ' + data.message);
        }
        
    } catch (error) {
        console.error('AI Chat Error:', error);
        hideTyping();
        input.disabled = false;
        btn.disabled = false;
        input.focus();
        appendMessage('ai', 'Something went wrong connecting to my brain. Please try again later.');
    }
}
