import { Response } from "express";

interface Client {
  userId: number;
  res: Response;
}

const clients = new Set<Client>();

export function addClient(userId: number, res: Response): () => void {
  const c: Client = { userId, res };
  clients.add(c);
  return () => clients.delete(c);
}

function write(res: Response, event: string, data: unknown): void {
  try {
    res.write(`event: ${event}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  } catch {}
}

export function sendToUser(userId: number, event: string, data: unknown): void {
  for (const c of clients) if (c.userId === userId) write(c.res, event, data);
}

export function broadcast(event: string, data: unknown, exceptUserId?: number): void {
  for (const c of clients) if (c.userId !== exceptUserId) write(c.res, event, data);
}

export function liveCount(): number {
  return clients.size;
}

export function isOnline(userId: number): boolean {
  for (const c of clients) if (c.userId === userId) return true;
  return false;
}
