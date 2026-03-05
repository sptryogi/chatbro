export type ModelType = 'gemini' | 'deepseek' | 'groq' | 'kimi';

export interface ChatSettings {
  temperature: number;
  topP: number;
  maxTokens: number;
  systemInstruction: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  attachments?: Attachment[];
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  model: ModelType;
  settings: ChatSettings;
  system_instruction?: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFile {
  id: string;
  filename: string;
  original_name: string;
  file_type: string;
  file_size: number;
  created_at: string;
}

export interface Attachment {
  type: 'image' | 'file';
  name: string;
  url?: string;
}