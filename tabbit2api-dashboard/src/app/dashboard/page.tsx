"use client";

import { useSession, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface Channel {
  id: string;
  name: string;
  created_at: number;
}

export default function Dashboard() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [apiKey, setApiKey] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelToken, setNewChannelToken] = useState("");

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/");
    } else if (status === "authenticated") {
      fetchDashboardData();
    }
  }, [status, router]);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      // 1. Fetch API Key
      const keyRes = await fetch("/api/keys");
      const keyData = await keyRes.json();
      setApiKey(keyData.key);

      // 2. Fetch Channels if key exists
      if (keyData.key) {
        const channelRes = await fetch("/api/channels");
        if (channelRes.ok) {
          const channelData = await channelRes.json();
          setChannels(channelData.channels || []);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const generateApiKey = async () => {
    try {
      const res = await fetch("/api/keys", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setApiKey(data.key);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const addChannel = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newChannelName,
          token_value: newChannelToken,
        }),
      });
      if (res.ok) {
        setIsModalOpen(false);
        setNewChannelName("");
        setNewChannelToken("");
        fetchDashboardData();
      } else {
        alert("Failed to add channel. Make sure the token is valid.");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const deleteChannel = async (id: string) => {
    if (!confirm("Are you sure you want to delete this channel?")) return;
    try {
      const res = await fetch(`/api/channels/${id}`, { method: "DELETE" });
      if (res.ok) {
        fetchDashboardData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  if (status === "loading" || loading) {
    return (
      <div className="container flex items-center justify-center" style={{ minHeight: "100vh" }}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="container mt-8">
      <div className="flex items-center justify-between" style={{ marginBottom: "2rem" }}>
        <h1>Control Panel</h1>
        <button className="outline" onClick={() => signOut()}>Sign Out</button>
      </div>

      <div className="card" style={{ marginBottom: "2rem" }}>
        <h2>Your API Key</h2>
        <p style={{ marginBottom: "1rem" }}>
          Use this key in your ChatBox or AI client as the Bearer token.
        </p>
        
        {apiKey ? (
          <div className="code-block flex items-center justify-between">
            <span>{apiKey}</span>
            <button 
              className="outline" 
              style={{ padding: "0.5rem 1rem" }}
              onClick={() => {
                navigator.clipboard.writeText(apiKey);
                alert("Copied to clipboard!");
              }}
            >
              Copy
            </button>
          </div>
        ) : (
          <button onClick={generateApiKey}>Generate API Key</button>
        )}
      </div>

      <div className="card">
        <div className="flex items-center justify-between" style={{ marginBottom: "1rem" }}>
          <h2>Private Channels</h2>
          <button onClick={() => setIsModalOpen(true)} disabled={!apiKey}>
            Add Channel
          </button>
        </div>
        
        {channels.length === 0 ? (
          <p className="text-center mt-4">No channels added yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Channel Name</th>
                <th>Created At</th>
                <th style={{ width: "100px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((ch) => (
                <tr key={ch.id}>
                  <td>{ch.name}</td>
                  <td>{new Date(ch.created_at * 1000).toLocaleString()}</td>
                  <td>
                    <button 
                      className="danger" 
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.8rem" }}
                      onClick={() => deleteChannel(ch.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="card modal-content" onClick={e => e.stopPropagation()}>
            <h2 style={{ marginBottom: "1.5rem" }}>Add Tabbit Channel</h2>
            <form onSubmit={addChannel} className="flex-col">
              <input
                type="text"
                placeholder="Channel Name (e.g. My Tabbit Sub)"
                value={newChannelName}
                onChange={(e) => setNewChannelName(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Tabbit Token (sk-...)"
                value={newChannelToken}
                onChange={(e) => setNewChannelToken(e.target.value)}
                required
              />
              <div className="flex justify-between mt-4">
                <button type="button" className="outline" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit">
                  Save Channel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
