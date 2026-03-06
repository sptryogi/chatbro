'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import ChatInterface from '@/components/ChatInterface';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // Double check auth di client side
    if (!api.isAuthenticated()) {
      router.push('/login');
    }
  }, [router]);

  return <ChatInterface />;
}
