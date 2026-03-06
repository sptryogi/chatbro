const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://chatbro-api.vercel.app';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('chatbro_token', token);
      // Set cookie untuk middleware (expires 7 hari)
      document.cookie = `chatbro_token=${token}; path=/; max-age=${7 * 24 * 60 * 60}; SameSite=Lax`;
    }
  }

  getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('chatbro_token');
    }
    return null;
  }

  // Tambahkan method untuk cek auth
  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  // Tambahkan method logout
  logout() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('chatbro_token');
      document.cookie = 'chatbro_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
      window.location.href = '/login';
    }
  }

  private async fetch(endpoint: string, options: RequestInit = {}) {
    const token = this.getToken();
    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
    };

    console.log(`API Request: ${API_URL}${endpoint}`);

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
      });

      // Log response status
      console.log(`Response: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        
        try {
          const errorData = await response.json();
          console.error('Error data:', errorData);
          // ✅ Fix: Ambil detail message dengan benar
          errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
        } catch (e) {
          // Kalau bukan JSON, ambil text
          const text = await response.text();
          errorMessage = text || errorMessage;
        }
        
        throw new Error(errorMessage);
      }

      return response.json();
    } catch (error: any) {
      console.error('Fetch error:', error);
      throw error;
    }
  }

    // Kalau 401, logout otomatis
    if (response.status === 401) {
      this.logout();
      throw new Error('Session expired. Please login again.');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Something went wrong');
    }

    return response.json();
  }

  // ... rest of methods sama
  async login(username: string, password: string) {
    const data = await this.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    this.setToken(data.token);
    return data;
  }

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
    
    if (response.status === 401) {
      this.logout();
      throw new Error('Session expired');
    }
    
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
