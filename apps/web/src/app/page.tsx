'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import ChatInterface from '@/components/ChatInterface';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (!api.isAuthenticated()) {
      router.replace('/login');
    }
  }, [router]);

  // Tampilkan loading atau null saat cek auth
  if (!api.isAuthenticated()) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return <ChatInterface />;
}
