import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";

const GATEWAY_URL = process.env.GATEWAY_URL || "http://api_gateway:8800";

async function getApiKey(userId: string) {
  const key = await prisma.apiKey.findFirst({ where: { userId } });
  return key?.key;
}

export async function DELETE(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const userId = (session.user as any).id;
  
  const apiKey = await getApiKey(userId);
  if (!apiKey) return NextResponse.json({ error: "No API Key found" }, { status: 400 });

  const { id } = await params;

  const response = await fetch(`${GATEWAY_URL}/v1/byok/channels/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${apiKey}` },
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
