import { API_ROUTES } from '@/config/env';
import { SYNC_EVENT } from '@/offline/syncEvents';
import { AiTaskChatPage } from '@/task/task_ai_chat/components/AiTaskChatPage';
import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import { response } from '../../test-utils/http';
import { iso, uid } from '../../test-utils/factories';
import { renderWithProviders } from '../../test-utils/renderWithProviders';
import { stubWindowEvents } from '../../test-utils/windowEvents';

const mockReplace = jest.fn();
const mockFetch = jest.fn();

const mockTaskId = uid('task');
const mockSessionId = uid('session');
const mockMessageId = uid('message');
const mockHistoryUrl = `${API_ROUTES.CHAT.HISTORY(mockSessionId)}?page=1&limit=20`;
let mockRouteTaskId: string | undefined = mockTaskId;
let mockHistoryMessages: unknown[] = [];
let mockReplyRole: 'ASSISTANT' | 'TOOL' = 'ASSISTANT';

jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({
    id: mockRouteTaskId,
  }),
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

beforeEach(() => {
  mockRouteTaskId = mockTaskId;
  mockHistoryMessages = [];
  mockReplyRole = 'ASSISTANT';
  mockReplace.mockReset();
  mockFetch.mockReset();
  mockFetch.mockImplementation((url: string, options?: RequestInit): Promise<Response> => {
    if (url === API_ROUTES.CHAT.CREATE_SESSION && options?.method === 'POST') {
      return Promise.resolve(
        response({
          session_id: mockSessionId,
        }),
      );
    }
    if (url === mockHistoryUrl && options?.method === 'GET') {
      return Promise.resolve(response(mockHistoryMessages));
    }
    if (url === API_ROUTES.CHAT.MESSAGE(mockSessionId) && options?.method === 'POST') {
      return Promise.resolve(
        response({
          id: mockMessageId,
          session_id: mockSessionId,
          role: mockReplyRole,
          content: "Task: 'Example task' updated with 3 subtasks!",
          created_at: iso(0),
          tool_call_id: null,
        }),
      );
    }
    return Promise.reject(new Error(`Unexpected request: ${options?.method} ${url}`));
  });
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

test('starts a chat session for the task', async () => {
  renderWithProviders(<AiTaskChatPage />);
  expect(screen.getByLabelText('Close task editor')).toBeTruthy();
  expect(screen.getByLabelText('Manual task mode')).toBeTruthy();
  expect(screen.getByLabelText('AI chat mode')).toBeTruthy();
  await waitFor(() =>
    expect(mockFetch).toHaveBeenCalledWith(API_ROUTES.CHAT.CREATE_SESSION, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({
        task_id: mockTaskId,
      }),
    }),
  );
  expect(await screen.findByPlaceholderText('State your goals...')).toBeTruthy();
  await waitFor(() =>
    expect(mockFetch).toHaveBeenCalledWith(mockHistoryUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    }),
  );
});

test('manual mode opens task edit', async () => {
  renderWithProviders(<AiTaskChatPage />);
  await waitFor(() =>
    expect(mockFetch).toHaveBeenCalledWith(
      mockHistoryUrl,
      expect.objectContaining({
        method: 'GET',
      }),
    ),
  );
  fireEvent.press(screen.getByLabelText('Manual task mode'));
  expect(mockReplace).toHaveBeenCalledWith(`/tasks/${mockTaskId}/edit`);
});

test('close opens task edit', async () => {
  renderWithProviders(<AiTaskChatPage />);
  await screen.findByPlaceholderText('State your goals...');
  fireEvent.press(screen.getByLabelText('Close task editor'));
  expect(mockReplace).toHaveBeenCalledWith(`/tasks/${mockTaskId}/edit`);
});

test('create mode returns to task creation', async () => {
  mockRouteTaskId = undefined;
  renderWithProviders(<AiTaskChatPage />);
  await screen.findByPlaceholderText('State your goals...');
  fireEvent.press(screen.getByLabelText('Manual task mode'));
  expect(mockReplace).toHaveBeenCalledWith('/tasks/create');
  fireEvent.press(screen.getByLabelText('Close task editor'));
  expect(mockReplace).toHaveBeenCalledWith('/tasks');
});

test('labels user and assistant messages', async () => {
  mockHistoryMessages = [
    {
      id: uid('ai-message'),
      session_id: mockSessionId,
      role: 'ASSISTANT',
      content: 'What would you like to change?',
      created_at: iso(0),
      tool_call_id: null,
    },
    {
      id: uid('user-message'),
      session_id: mockSessionId,
      role: 'USER',
      content: 'Add one testing subtask.',
      created_at: iso(1),
      tool_call_id: null,
    },
  ];
  renderWithProviders(<AiTaskChatPage />);
  expect(await screen.findByLabelText('AI message')).toBeTruthy();
  expect(screen.getByLabelText('Your message')).toBeTruthy();
});

test('labels task confirmation as an AI message', async () => {
  mockHistoryMessages = [
    {
      id: uid('tool-message'),
      session_id: mockSessionId,
      role: 'TOOL',
      content: "Task: 'Example task' created with 3 subtasks!",
      created_at: iso(2),
      tool_call_id: 'tool-call-1',
    },
  ];
  renderWithProviders(<AiTaskChatPage />);
  expect(await screen.findByLabelText('AI message')).toBeTruthy();
});

test('sends a message to the chat session', async () => {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  renderWithProviders(<AiTaskChatPage />);
  await waitFor(() =>
    expect(mockFetch).toHaveBeenCalledWith(mockHistoryUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    }),
  );
  const input = screen.getByPlaceholderText('State your goals...');
  fireEvent.changeText(input, 'Reduce this roadmap to three subtasks');
  fireEvent.press(screen.getByLabelText('Send message'));
  await waitFor(() =>
    expect(mockFetch).toHaveBeenCalledWith(API_ROUTES.CHAT.MESSAGE(mockSessionId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({
        msg: 'Reduce this roadmap to three subtasks',
        tz,
      }),
    }),
  );
});

test('requests task sync after task confirmation', async () => {
  mockReplyRole = 'TOOL';
  const restoreWindowEvents = stubWindowEvents();
  const handleSync = jest.fn();
  window.addEventListener(SYNC_EVENT, handleSync);
  let view: ReturnType<typeof renderWithProviders> | undefined;
  try {
    view = renderWithProviders(<AiTaskChatPage />);
    const input = await screen.findByPlaceholderText('State your goals...');
    fireEvent.changeText(input, 'Create a task with three steps');
    fireEvent.press(screen.getByLabelText('Send message'));
    await waitFor(() => expect(handleSync).toHaveBeenCalledTimes(1));
  } finally {
    window.removeEventListener(SYNC_EVENT, handleSync);
    view?.unmount();
    restoreWindowEvents();
  }
});
