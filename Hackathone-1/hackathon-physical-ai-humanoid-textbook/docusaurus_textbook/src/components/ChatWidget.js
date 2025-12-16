import { useState } from 'react';
import axios from 'axios';
import './chat.css';

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = { sender: "user", text: input };
    const currentInput = input;

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      console.log("Sending message:", currentInput);

      // Try local backend first, then fall back to external
      const backendUrl = "http://localhost:8000";

      const res = await axios.post(`${backendUrl}/ask`, {
        query: currentInput
      }, {
        headers: {
          'Content-Type': 'application/json'
        },
        timeout: 30000
      });

      console.log("Response received:", res);
      console.log("Response data:", res.data);

      const botReply = res.data.answer || res.data.reply || res.data.response || res.data.message || "No response from server";
      const sources = res.data.sources || [];
      const sourcesText = sources.length > 0 ? `\n\nSources: ${sources.join(', ')}` : '';

      const botMessage = {
        sender: "bot",
        text: `${botReply}${sourcesText}`
      };

      setMessages(prev => [...prev, botMessage]);
    } catch (err) {
      console.error("Chat error details:", err);
      console.error("Error response:", err.response);
      console.error("Error message:", err.message);

      let errorMsg = "Unable to reach server";

      if (err.response) {
        errorMsg = err.response?.data?.error || err.response?.data?.detail || err.message;
      } else if (err.message === 'Network Error') {
        errorMsg = "Network Error: Backend server not responding. Please ensure the backend is running on port 8000";
      } else {
        errorMsg = err.message || "Unknown error occurred";
      }

      setMessages(prev => [...prev, {
        sender: "bot",
        text: `❌ Error: ${errorMsg}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !loading) {
      sendMessage();
    }
  };

  return (
    <div className="chat-container">
      <button className="chat-button" onClick={() => setOpen(!open)}>
        💬 Chat
      </button>
      {open && (
        <div className="chat-box">
          <div className="chat-header">
            <strong>AI Assistant</strong>
          </div>
          <div className="chat-body">
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.sender}`}>
                {m.text}
              </div>
            ))}
            {loading && (
              <div className="bubble bot">
                <em>Typing...</em>
              </div>
            )}
          </div>
          <div className="chat-input">
            <input 
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type message..."
              disabled={loading}
            />
            <button onClick={sendMessage} disabled={loading}>
              {loading ? "..." : "Send"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
