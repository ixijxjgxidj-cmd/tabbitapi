import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/lib/auth";

export async function GET(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const userId = (session.user as any).id;

  const key = await prisma.apiKey.findFirst({
    where: { userId },
  });

  return NextResponse.json({ key: key?.key || null });
}

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const userId = (session.user as any).id;

  const existingKey = await prisma.apiKey.findFirst({
    where: { userId },
  });

  if (existingKey) {
    return NextResponse.json({ error: "Key already exists" }, { status: 400 });
  }

  // Generate an sk-UUID format key
  const randomUUID = crypto.randomUUID().replace(/-/g, "");
  const newKey = `sk-${randomUUID}`;

  const apiKey = await prisma.apiKey.create({
    data: {
      key: newKey,
      userId,
    },
  });

  return NextResponse.json({ key: apiKey.key }, { status: 201 });
}
