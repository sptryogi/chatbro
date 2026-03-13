'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Settings, Plus, LogOut, Menu, Bot, User, FileText, Image as ImageIcon, X, ChevronLeft, ChevronRight, Pencil, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { ModelType, Message, ChatSession, KnowledgeFile, ChatSettings } from '@/types';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const MODELS: { id: ModelType; name: string; color: string; description: string }[] = [
  { id: 'gemini', name: 'Gemini Pro', color: 'bg-blue-500', description: 'Google Gemini Pro' },
  { id: 'deepseek', name: 'DeepSeek', color: 'bg-purple-500', description: 'DeepSeek Chat' },
  { id: 'groq', name: 'Groq', color: 'bg-orange-500', description: 'Groq (Mixtral)' },
  { id: 'kimi', name: 'Kimi', color: 'bg-emerald-500', description: 'Moonshot Kimi' },
];

const DEFAULT_SETTINGS: ChatSettings = {
  temperature: 0.7,
  topP: 0.9,
  maxTokens: 2048,
  systemInstruction: 'You are a helpful AI assistant.',
};

export default function ChatInterface() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<ModelType>('gemini');
  const [settings, setSettings] = useState<ChatSettings>(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [showDrivePicker, setShowDrivePicker] = useState(false);
  const [knowledgeFiles, setKnowledgeFiles] = useState<KnowledgeFile[]>([]);
  const [selectedKnowledge, setSelectedKnowledge] = useState<string[]>([]);
  const [showKnowledge, setShowKnowledge] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadSessions();
    loadKnowledge();
  }, []);

  useEffect(() => {
    if (currentSession) {
      loadMessages(currentSession.id);
      setSelectedModel(currentSession.model);
      setSettings({ ...DEFAULT_SETTINGS, ...currentSession.settings });
    }
  }, [currentSession]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadSessions = async () => {
    try {
      const data = await api.getSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadMessages = async (sessionId: string) => {
    try {
      const data = await api.getMessages(sessionId);
      setMessages(data);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const loadKnowledge = async () => {
    try {
      const data = await api.getKnowledge();
      setKnowledgeFiles(data);
    } catch (error) {
      console.error('Failed to load knowledge:', error);
    }
  };

  const createNewSession = async (): Promise<ChatSession | null> => {
    try {
      const session = await api.createSession({
        title: 'New Chat',
        model: selectedModel,
        settings: settings,
        system_instruction: settings.systemInstruction,
      });
      setSessions([session, ...sessions]);
      setCurrentSession(session);
      setMessages([]);
      return session; // ✅ Tambahkan return
    } catch (error) {
      console.error('Failed to create session:', error);
      return null; // ✅ Return null kalau error
    }
  };

  const generateTitleFromMessage = (content: string): string => {
    // Ambil 3 kata pertama
    const words = content.trim().split(/\s+/).slice(0, 3);
    let title = words.join(' ');
    // Tambah ellipsis kalau panjang
    if (content.trim().split(/\s+/).length > 3) {
      title += '...';
    }
    // Max 50 chars
    return title.length > 50 ? title.substring(0, 50) + '...' : title;
  };
  
  const handleSend = async () => {
    if (!input.trim() && attachments.length === 0) return;
    
    // ✅ Fix: Buat session dulu kalau belum ada
    let session = currentSession;
    if (!session) {
      const newSession = await createNewSession();
      if (!newSession) {
        console.error('Failed to create session');
        return;
      }
      session = newSession;
    }
  
    const userContent = input;
    setInput('');
    
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userContent,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // ✅ Fix: Pastikan session sudah ada sebelum save message
      await api.addMessage(session.id, 'user', userContent);

      // Get knowledge context
      let knowledgeContext = '';
      if (selectedKnowledge.length > 0) {
        for (const fileId of selectedKnowledge) {
          try {
            const content = await api.getKnowledgeContent(fileId);
            knowledgeContext += content.content + '\n\n';
          } catch (e) {
            console.error('Knowledge fetch error:', e);
          }
        }
      }

      // Prepare messages - ✅ Fix: jangan include system message di array, sudah di backend
      const apiMessages = messages.concat(userMessage).map(m => ({
        role: m.role,
        content: m.content,
      })).filter(m => m.role !== 'system'); // Filter out system messages

      console.log('Sending chat request:', { model: selectedModel, messageCount: apiMessages.length }); // ✅ Log

      const response = await api.chat({
        model: selectedModel,
        messages: apiMessages,
        temperature: settings.temperature,
        top_p: settings.topP,
        max_tokens: settings.maxTokens,
        system_instruction: settings.systemInstruction,
        knowledge_context: knowledgeContext || undefined,
      });

      // Ambil konten response dengan aman
      const aiContent = response.response || response.message || (typeof response === 'string' ? response : '');

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: aiContent,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMessage]);

      // Kirim aiContent, bukan response.response yang berpotensi undefined
      await api.addMessage(session.id, 'assistant', aiContent);

      // Update title hanya jika title masih default dan aiContent ada
      if (session && (session.title === 'New Chat' || !session.title) && aiContent) {
        const newTitle = generateTitleFromMessage(aiContent);
        if (newTitle) { // Pastikan title tidak kosong
           await api.updateSession(session.id, newTitle);
           // Update local state
           setSessions(prev => prev.map(s => 
             s.id === session.id ? { ...s, title: newTitle } : s
           ));
           if (currentSession?.id === session.id) {
             setCurrentSession({ ...session, title: newTitle });
           }
        }
      }
      
    } catch (error: any) {
      // ✅ Fix: Better error message extraction
      let errorMsg = 'Unknown error';
      if (error instanceof Error) {
        errorMsg = error.message;
      } else if (typeof error === 'string') {
        errorMsg = error;
      } else {
        errorMsg = JSON.stringify(error);
      }
      
      console.error('Chat error:', errorMsg);
      
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `❌ Error: ${errorMsg}`,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    for (const file of Array.from(files)) {
      try {
        await api.uploadKnowledge(file);
        loadKnowledge();
      } catch (error) {
        console.error('Upload failed:', error);
      }
    }
  };

  const handleAttachFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      setAttachments(prev => [...prev, ...Array.from(files)]);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <div className={cn(
        "fixed inset-y-0 left-0 z-50 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out",
        // Logika Desktop
        sidebarHidden ? "lg:w-0 lg:-translate-x-full" : "lg:w-80 lg:translate-x-0",
        // Logika Mobile
        showSidebar ? "translate-x-0 w-80" : "-translate-x-full w-80",
        "lg:relative" // Tetap relative agar mengambil ruang saat muncul
      )}>
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  ChatBro
                </span>
              </div>
              
              {/* Tombol Hide Sidebar - di kanan atas sidebar */}
              <button
                onClick={() => setSidebarHidden(true)}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Hide Sidebar"
              >
                <ChevronLeft className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <button
              onClick={createNewSession}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto p-2">
            {sessions.map(session => (
              <div
                key={session.id}
                className={cn(
                  "group flex items-center justify-between p-3 rounded-lg mb-1 transition-colors",
                  currentSession?.id === session.id
                    ? "bg-blue-50 dark:bg-blue-900/20 border-l-2 border-blue-500"
                    : "hover:bg-gray-100 dark:hover:bg-gray-700"
                )}
              >
                <button
                  onClick={() => setCurrentSession(session)}
                  className="flex-1 text-left min-w-0"
                >
                  <p className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                    {session.title}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {MODELS.find(m => m.id === session.model)?.name}
                  </p>
                </button>
                
                {/* Action buttons - muncul saat hover */}
                <div className="hidden group-hover:flex items-center gap-1 ml-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      const newTitle = prompt('Rename chat:', session.title);
                      if (newTitle && newTitle.trim()) {
                        api.updateSession(session.id, newTitle.trim()).then(() => loadSessions());
                      }
                    }}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
                    title="Rename"
                  >
                    <Pencil className="w-3 h-3 text-gray-500" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Delete this chat?')) {
                        api.deleteSession(session.id).then(() => {
                          if (currentSession?.id === session.id) {
                            setCurrentSession(null);
                            setMessages([]);
                          }
                          loadSessions();
                        });
                      }
                    }}
                    className="p-1 hover:bg-red-100 dark:hover:bg-red-900 rounded"
                    title="Delete"
                  >
                    <Trash2 className="w-3 h-3 text-red-500" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Knowledge Base */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setShowKnowledge(!showKnowledge)}
              className="w-full flex items-center justify-between p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            >
              <span className="text-sm font-medium">Knowledge Base</span>
              <FileText className="w-4 h-4" />
            </button>
            
            {showKnowledge && (
              <div className="mt-2 space-y-2">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".pdf,.docx,.txt,.jpg,.jpeg,.png"
                  className="hidden"
                  multiple
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full text-xs px-3 py-2 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  + Upload File
                </button>

                <button
                  onClick={() => setShowDrivePicker(true)}
                  className="w-full text-xs px-3 py-2 border border-dashed border-blue-300 dark:border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20"
                >
                  + Import from Google Drive
                </button>
                
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {knowledgeFiles.map(file => (
                    <div
                      key={file.id}
                      className="flex items-center gap-2 p-2 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 rounded group"
                    >
                      <input
                        type="checkbox"
                        checked={selectedKnowledge.includes(file.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedKnowledge([...selectedKnowledge, file.id]);
                          } else {
                            setSelectedKnowledge(selectedKnowledge.filter(id => id !== file.id));
                          }
                        }}
                        className="rounded"
                      />
                      <span className="truncate flex-1">{file.original_name}</span>
                      <span className="text-gray-400">{formatFileSize(file.file_size)}</span>
                      
                      {/* Delete button */}
                      <button
                        onClick={() => {
                          if (confirm(`Delete ${file.original_name}?`)) {
                            api.deleteKnowledge(file.id).then(() => {
                              // Remove from selected kalau ada
                              setSelectedKnowledge(prev => prev.filter(id => id !== file.id));
                              loadKnowledge();
                            });
                          }
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 rounded transition-opacity"
                      >
                        <Trash2 className="w-3 h-3 text-red-500" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <div className="h-16 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-4">
            {/* Tombol Menu Mobile */}
            <button
              onClick={() => setShowSidebar(true)}
              className="lg:hidden p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            >
              <Menu className="w-5 h-5" />
            </button>
            
            {/* Tombol Unhide Sidebar Desktop */}
            {sidebarHidden && (
              <button
                onClick={() => setSidebarHidden(false)}
                className="hidden lg:flex p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                title="Show Sidebar"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            )}
            
            {/* Model Selector */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">Model:</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value as ModelType)}
                className="px-3 py-1.5 bg-gray-100 dark:bg-gray-700 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {MODELS.map(model => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={cn(
                "p-2 rounded-lg transition-colors",
                showSettings ? "bg-blue-100 dark:bg-blue-900 text-blue-600" : "hover:bg-gray-100 dark:hover:bg-gray-700"
              )}
            >
              <Settings className="w-5 h-5" />
            </button>
            
            {/* Tambahkan tombol logout */}
            <button
              onClick={() => api.logout()}
              className="p-2 hover:bg-red-100 dark:hover:bg-red-900 text-gray-600 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg transition-colors"
              title="Logout"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Settings Panel */}
        {showSettings && (
          <div className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
            <div className="max-w-2xl mx-auto space-y-4">
              <h3 className="font-medium text-sm text-gray-900 dark:text-gray-100">Model Settings</h3>
              
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Temperature</label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={settings.temperature}
                    onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <span className="text-xs text-gray-600">{settings.temperature}</span>
                </div>
                
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Top P</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={settings.topP}
                    onChange={(e) => setSettings({ ...settings, topP: parseFloat(e.target.value) })}
                    className="w-full"
                  />
                  <span className="text-xs text-gray-600">{settings.topP}</span>
                </div>
                
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Max Tokens</label>
                  <input
                    type="number"
                    value={settings.maxTokens}
                    onChange={(e) => setSettings({ ...settings, maxTokens: parseInt(e.target.value) })}
                    className="w-full px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-gray-500 block mb-1">System Instruction</label>
                <textarea
                  value={settings.systemInstruction}
                  onChange={(e) => setSettings({ ...settings, systemInstruction: e.target.value })}
                  rows={3}
                  className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  placeholder="Enter system instructions for the AI..."
                />
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg">
                <Bot className="w-8 h-8 text-white" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                Welcome to ChatBro
              </h2>
              <p className="text-gray-500 max-w-md">
                Start a conversation with multiple AI models. Upload knowledge files to enhance responses.
              </p>
              <div className="flex gap-2 mt-6">
                {MODELS.map(model => (
                  <button
                    key={model.id}
                    onClick={() => setSelectedModel(model.id)}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                      selectedModel === model.id
                        ? "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300"
                        : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200"
                    )}
                  >
                    {model.name}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, idx) => (
              <div
                key={message.id}
                className={cn(
                  "flex gap-4 max-w-4xl mx-auto",
                  message.role === 'user' ? "flex-row-reverse" : "flex-row"
                )}
              >
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                  message.role === 'user' 
                    ? "bg-blue-600" 
                    : "bg-gradient-to-br from-purple-500 to-pink-500"
                )}>
                  {message.role === 'user' 
                    ? <User className="w-4 h-4 text-white" />
                    : <Bot className="w-4 h-4 text-white" />
                  }
                </div>
                
                <div className={cn(
                  "flex-1 px-4 py-3 rounded-2xl",
                  message.role === 'user'
                    ? "bg-blue-600 text-white rounded-br-md"
                    : "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-bl-md shadow-sm"
                )}>
                  {message.role === 'assistant' ? (
                    <div className="prose dark:prose-invert prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm">{message.content}</p>
                  )}
                </div>
              </div>
            ))
          )}
          {isLoading && (
            <div className="flex gap-4 max-w-4xl mx-auto">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div className="flex-1 px-4 py-3 rounded-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-bl-md shadow-sm">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="max-w-4xl mx-auto">
            {/* Attachments Preview */}
            {attachments.length > 0 && (
              <div className="flex gap-2 mb-2 flex-wrap">
                {attachments.map((file, idx) => (
                  <div key={idx} className="flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs">
                    <span className="truncate max-w-[150px]">{file.name}</span>
                    <button 
                      onClick={() => setAttachments(attachments.filter((_, i) => i !== idx))}
                      className="hover:text-red-500"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            
            <div className="flex gap-2 items-end">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleAttachFile}
                className="hidden"
                multiple
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <Paperclip className="w-5 h-5" />
              </button>
              
              <div className="flex-1 relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Message ChatBro..."
                  rows={1}
                  className="w-full px-4 py-3 bg-gray-100 dark:bg-gray-700 border-0 rounded-xl resize-none focus:ring-2 focus:ring-blue-500 focus:outline-none max-h-32"
                  style={{ minHeight: '52px' }}
                />
              </div>
              
              <button
                onClick={handleSend}
                disabled={isLoading || (!input.trim() && attachments.length === 0)}
                className="p-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            
            <p className="text-center text-xs text-gray-400 mt-2">
              ChatBro may produce inaccurate information. Verify important information.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
