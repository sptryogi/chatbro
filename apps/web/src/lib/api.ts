const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://chatbro-api.vercel.app/';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('chatbro_token', token);
    }
  }

  getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('chatbro_token');
    }
    return null;
  }

  private async fetch(endpoint: string, options: RequestInit = {}) {
    const token = this.getToken();
    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
    };

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Something went wrong');
    }

    return response.json();
  }

  // Auth
  async login(username: string, password: string) {
    const data = await this.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    this.setToken(data.token);
    return data;
  }

  // Chat
  async chat(params: {
    model: string;
    messages: Array<{ role: string; content: string }>;
    temperature: number;
    top_p: number;
    max_tokens: number;
    system_instruction?: string;
    knowledge_context?: string;
  }) {
    return this.fetch('/chat', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  // Sessions
  async createSession(session: {
    title: string;
    model: string;
    settings: object;
    system_instruction?: string;
  }) {
    return this.fetch('/sessions', {
      method: 'POST',
      body: JSON.stringify(session),
    });
  }

  async getSessions() {
    return this.fetch('/sessions');
  }

  async getMessages(sessionId: string) {
    return this.fetch(`/sessions/${sessionId}/messages`);
  }

  async addMessage(sessionId: string, role: string, content: string) {
    return this.fetch(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ role, content }),
    });
  }

  // Knowledge
  async uploadKnowledge(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    
    const token = this.getToken();
    const response = await fetch(`${API_URL}/knowledge/upload`, {
      method: 'POST',
      headers: {
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
      body: formData,
    });
    
    if (!response.ok) throw new Error('Upload failed');
    return response.json();
  }

  async getKnowledge() {
    return this.fetch('/knowledge');
  }

  async getKnowledgeContent(fileId: string) {
    return this.fetch(`/knowledge/${fileId}/content`);
  }

  async deleteKnowledge(fileId: string) {
    return this.fetch(`/knowledge/${fileId}`, { method: 'DELETE' });
  }
}

export const api = new ApiClient();
