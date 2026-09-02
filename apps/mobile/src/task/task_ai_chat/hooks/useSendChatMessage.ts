import { API_ROUTES } from '@/config/env';
import { requestSync } from '@/offline/syncEvents';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ChatMessage } from '../schemas';

type SendMessageArgs = {
  message: string;
};

const sendChatMessage =
  (sessionId: string) =>
  async ({ message }: SendMessageArgs): Promise<ChatMessage> => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const res = await fetch(API_ROUTES.CHAT.MESSAGE(sessionId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ msg: message, tz }),
    });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  };

export default function useSendChatMessage(sessionId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: sessionId
      ? sendChatMessage(sessionId)
      : async () => {
          throw new Error('Chat session is not ready');
        },
    onSuccess: (message) => {
      if (message.role === 'TOOL') requestSync();
    },
    onSettled: () => {
      client.invalidateQueries({
        queryKey: ['chat', 'history', sessionId],
      });
    },
  });
}
