import React, { useState } from 'react';
import { Upload, Link, Loader2 } from 'lucide-react';
import axios from 'axios';
import { cn } from '../lib/utils';

// Configure base URL (hardcoded for now, ideal to use env)
const API_URL = "http://localhost:8000";

interface VideoInputProps {
    onVideoSelected: (videoData: any) => void;
}

export const VideoInput: React.FC<VideoInputProps> = ({ onVideoSelected }) => {
    const [url, setUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'url' | 'upload'>('url');

    const handleUrlSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!url) return;

        setLoading(true);
        setError(null);
        try {
            const response = await axios.post(`${API_URL}/download`, { url });
            onVideoSelected(response.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to download video");
        } finally {
            setLoading(false);
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setLoading(true);
        setError(null);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post(`${API_URL}/upload`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            onVideoSelected(response.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to upload video");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full max-w-2xl mx-auto p-6 bg-card rounded-xl shadow-sm border">
            <div className="flex space-x-4 mb-6">
                <button
                    onClick={() => setActiveTab('url')}
                    className={cn(
                        "flex items-center px-4 py-2 rounded-lg transition-colors",
                        activeTab === 'url' ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                    )}
                >
                    <Link className="h-4 w-4 mr-2" />
                    YouTube URL
                </button>
                <button
                    onClick={() => setActiveTab('upload')}
                    className={cn(
                        "flex items-center px-4 py-2 rounded-lg transition-colors",
                        activeTab === 'upload' ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                    )}
                >
                    <Upload className="h-4 w-4 mr-2" />
                    Upload File
                </button>
            </div>

            {activeTab === 'url' ? (
                <form onSubmit={handleUrlSubmit} className="space-y-4">
                    <div>
                        <input
                            type="url"
                            placeholder="Paste YouTube Link (e.g. https://youtube.com/watch?v=...)"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            className="w-full p-3 rounded-lg border bg-background focus:ring-2 focus:ring-primary focus:outline-none"
                            required
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50 flex justify-center items-center"
                    >
                        {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Start Processing"}
                    </button>
                </form>
            ) : (
                <div className="border-2 border-dashed rounded-lg p-10 text-center hover:bg-muted/50 transition-colors relative">
                    <input
                        type="file"
                        accept="video/*"
                        onChange={handleFileUpload}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        disabled={loading}
                    />
                    <div className="flex flex-col items-center pointer-events-none">
                        {loading ? (
                            <Loader2 className="h-10 w-10 animate-spin text-muted-foreground mb-4" />
                        ) : (
                            <Upload className="h-10 w-10 text-muted-foreground mb-4" />
                        )}
                        <p className="text-lg font-medium">Click or Drag & Drop to Upload</p>
                        <p className="text-sm text-muted-foreground mt-2">MP4, MKV, MOV supported</p>
                    </div>
                </div>
            )}

            {error && (
                <div className="mt-4 p-4 bg-destructive/10 text-destructive rounded-lg text-sm">
                    {error}
                </div>
            )}
        </div>
    );
};
