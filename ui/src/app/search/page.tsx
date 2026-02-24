"use client";

import { useState, useEffect } from "react";
import { Search, Filter, Video, Camera, Calendar, Clock, Play, ArrowRight, ArrowLeft, Link2 } from "lucide-react";

interface Detection {
  id: string;
  track_id: number;
  timestamp: string;
  image_url?: string;
  category: string;
  class_name: string;
  color_profile: Record<string, number>;
  camera_id: string;
}

interface DetectionDetail {
  track_id: number;
  timestamp: string;
  image_url: string;
  category: string;
  class_name: string;
  color_profile: Record<string, number>;
  camera_id: string;
  id: string;
  person_id: string | null;
  video_id: string;
  video_time_offset: number;
}

interface VideoInfo {
  id: string;
  camera_id: string;
  label: string;
  filename: string;
  file_path: string;
  status: string;
  created_at: string;
}

interface CameraRelationship {
  camera_id: string;
  relationship_type: 'incoming' | 'outgoing';
  avg_transition_time: number | null;
  description: string;
}


export default function SearchPage() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [cameras, setCameras] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCamera, setSelectedCamera] = useState("");
  const [selectedVideo, setSelectedVideo] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"detections" | "videos">("detections");
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null);
  const [detectionDetail, setDetectionDetail] = useState<DetectionDetail | null>(null);
  const [imageTarget, setImageTarget] = useState<Detection | null>(null);
  const [videoTimeOffset, setVideoTimeOffset] = useState<string | null>(null);
  const [cameraRelationships, setCameraRelationships] = useState<CameraRelationship[]>([]);
  const [showRelationships, setShowRelationships] = useState(false);

  // ดึงค่า video และ time จาก URL parameters
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const videoId = urlParams.get('video');
    const time = urlParams.get('time');
    const timestamp = urlParams.get('timestamp');
    const camera_id = urlParams.get('camera_id');
    const clothing_class = urlParams.get('clothing_class');
    const color = urlParams.get('color');
    const confidence = urlParams.get('confidence');
    const tab = urlParams.get('tab');
    
    // ถ้ามี camera_id ให้ตั้งค่า selectedCamera
    if (camera_id) {
      setSelectedCamera(camera_id);
    }
    
    // ถ้ามี tab=videos ให้เปลี่ยนไปที่ videos tab
    if (tab === 'videos') {
      setActiveTab("videos");
    }
    
    if (videoId) {
      setSelectedVideo(videoId);
      setActiveTab("videos"); // เปลี่ยนไปที่ video tab
      setPlayingVideoId(videoId); // เริ่มเล่น video
      
      // ถ้ามี time parameter ให้ seek ไปที่เวลานั้น
      if (time) {
        setVideoTimeOffset(time);
        console.log(`Should seek to time: ${time}s for video: ${videoId}`);
      }
      
      // สร้าง imageTarget จาก URL parameters
      if (timestamp && camera_id && clothing_class && color && confidence) {
        const mockImageTarget: Detection = {
          id: 'from-url',
          track_id: 0,
          timestamp: timestamp,
          image_url: undefined,
          category: color,
          class_name: clothing_class,
          color_profile: {},
          camera_id: camera_id
        };
        setImageTarget(mockImageTarget);
      }
    }
  }, []);

  // Fetch detection detail when imageTarget changes
  useEffect(() => {
    if (!imageTarget || imageTarget.id === 'from-url') {
      setDetectionDetail(null);
      return;
    }

    const fetchDetectionDetail = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/detections/${encodeURIComponent(imageTarget.id)}`);
        if (!response.ok) {
          throw new Error("Failed to fetch detection details");
        }
        const data = await response.json();
        setDetectionDetail(data);
      } catch (error) {
        console.error("Error fetching detection detail:", error);
        setDetectionDetail(null);
      }
    };

    fetchDetectionDetail();
  }, [imageTarget]);

  // ดึงข้อมูล detections
  const fetchDetections = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCamera) params.append("camera_id", selectedCamera);
      if (selectedVideo) params.append("video_id", selectedVideo);
      
      const response = await fetch(`/api/video/detections?${params.toString()}`);
      const data = await response.json();
      
      // Ensure data is an array
      setDetections(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error("Error fetching detections:", error);
      setDetections([]);
    } finally {
      setLoading(false);
    }
  };

  // ดึงข้อมูลกล้อง
  const fetchCameras = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras`);
      const data = await response.json();
      
      // Ensure data is an array
      setCameras(Array.isArray(data.cameras) ? data.cameras : []);
    } catch (error) {
      console.error("Error fetching cameras:", error);
      setCameras([]);
    }
  };

  // ดึงข้อมูลวิดีโอ
  const fetchVideos = async () => {
    try {
      const response = await fetch("/api/video/videos");
      const data = await response.json();
      
      // Ensure data is an array
      setVideos(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error("Error fetching videos:", error);
      setVideos([]);
    }
  };

  // ดึงข้อมูลความสัมพันธ์ของกล้อง
  const fetchCameraRelationships = async (cameraId: string) => {
    if (!cameraId) {
      setCameraRelationships([]);
      return;
    }
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${encodeURIComponent(cameraId)}/relationships`);
      const data = await response.json();
      setCameraRelationships(data.relationships || []);
    } catch (error) {
      console.error("Error fetching camera relationships:", error);
      setCameraRelationships([]);
    }
  };

  
  useEffect(() => {
    fetchCameras();
    fetchDetections();
    fetchVideos();
  }, [selectedCamera, selectedVideo]);

  // ดึงข้อมูลความสัมพันธ์เมื่อเลือกกล้อง
  useEffect(() => {
    fetchCameraRelationships(selectedCamera);
  }, [selectedCamera]);

  // กรอง detections ตามคำค้นหา
  const filteredDetections = Array.isArray(detections) ? detections.filter(detection => {
    const matchesSearch = detection.class_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         detection.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         detection.camera_id.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  }) : [];

  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1
            className="font-orbitron text-xl font-bold text-green-400 tracking-[0.2em] uppercase glitch-text"
            data-text="SEARCH"
          >
            SEARCH
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            VIDEO & CAMERA SEARCH · DETECTION RESULTS
          </p>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex flex-wrap gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by clothing type, category, or camera..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 bg-transparent border-none outline-none text-sm text-slate-300 placeholder:text-slate-500"
          />
        </div>

        <select
          value={selectedCamera}
          onChange={(e) => setSelectedCamera(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm text-slate-300"
        >
          <option value="">All Cameras</option>
          {Array.isArray(cameras) && cameras.map(camera => (
            <option key={camera.id} value={camera.name}>{camera.name}</option>
          ))}
        </select>

        <select
          value={selectedVideo}
          onChange={(e) => setSelectedVideo(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm text-slate-300"
        >
          <option value="">All Videos</option>
          {Array.isArray(videos) && videos.map(video => (
            <option key={video.id} value={video.id}>{video.filename}</option>
          ))}
        </select>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab("detections")}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              activeTab === "detections" 
                ? "bg-green-600 text-white" 
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            }`}
          >
            Detections ({filteredDetections.length})
          </button>
          <button
            onClick={() => setActiveTab("videos")}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              activeTab === "videos" 
                ? "bg-green-600 text-white" 
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            }`}
          >
            Videos ({videos.length})
          </button>
        </div>
      </div>

      {/* Camera Relationships */}
      {selectedCamera && cameraRelationships.length > 0 && (
        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Link2 className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-mono text-cyan-400 uppercase tracking-wider">
                กล้องที่สัมพันธ์กับ {selectedCamera}
              </h3>
            </div>
            <button
              onClick={() => setShowRelationships(!showRelationships)}
              className="text-xs text-slate-400 hover:text-slate-300 transition-colors"
            >
              {showRelationships ? 'ซ่อน' : 'แสดง'}
            </button>
          </div>
          
          {showRelationships && (
            <div className="space-y-2">
              {cameraRelationships.map((rel, index) => (
                <div 
                  key={index}
                  className="flex items-center justify-between p-2 bg-slate-800/50 rounded border border-slate-700/50"
                >
                  <div className="flex items-center gap-2">
                    {rel.relationship_type === 'outgoing' ? (
                      <ArrowRight className="w-3 h-3 text-green-400" />
                    ) : (
                      <ArrowLeft className="w-3 h-3 text-blue-400" />
                    )}
                    <span className="text-sm text-slate-300">
                      {rel.relationship_type === 'outgoing' ? 'ไปยัง' : 'มาจาก'} 
                    </span>
                    <button
                      onClick={() => setSelectedCamera(rel.camera_id)}
                      className="ml-1 font-mono text-cyan-300 hover:text-cyan-200 underline decoration-1 underline-offset-2 transition-colors"
                    >
                      {rel.camera_id}
                    </button>
                  </div>
                  {rel.avg_transition_time && (
                    <span className="text-xs text-slate-500">
                      {rel.avg_transition_time}วินาที
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Results */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-slate-400">Loading...</div>
          </div>
        ) : activeTab === "detections" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredDetections.map((detection) => (
              <div
                key={detection.id}
                className="bg-slate-900/50 border border-slate-800 rounded-lg p-3 hover:border-slate-600 transition-colors"
              >
                {detection.image_url && (
                  <img
                    src={detection.image_url}
                    alt={detection.class_name}
                    className="w-full h-32 object-cover rounded mb-2"
                  />
                )}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-green-400">{detection.camera_id}</span>
                    <span className="text-xs text-slate-500">{detection.category}</span>
                  </div>
                  <div className="font-semibold text-sm text-slate-200">{detection.class_name}</div>
                  <div className="text-xs text-slate-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(detection.timestamp).toLocaleString()}
                  </div>
                  {Object.keys(detection.color_profile).length > 0 && (
                    <div className="text-xs text-slate-400">
                      Colors: {Object.keys(detection.color_profile).slice(0, 3).join(", ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {Array.isArray(videos) && videos.map((video) => (
              <div
                key={video.id}
                className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 hover:border-slate-600 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Video className="w-5 h-5 text-blue-400" />
                    <div className="flex-1">
                      <div className="font-semibold text-slate-200">{video.filename}</div>
                      <div className="text-xs text-slate-400">
                        {video.camera_id} • {video.label}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className={`text-xs px-2 py-1 rounded ${
                      video.status === "processing" 
                        ? "bg-yellow-900/50 text-yellow-400" 
                        : "bg-green-900/50 text-green-400"
                    }`}>
                      {video.status}
                    </div>
                    <div className="text-xs text-slate-500">
                      {new Date(video.created_at).toLocaleString()}
                    </div>
                    {video.status === "completed" && (
                      <button
                        onClick={() => setPlayingVideoId(playingVideoId === video.id ? null : video.id)}
                        className="p-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
                
                {/* Video Player */}
                {playingVideoId === video.id && (
                  <div className="mt-4 rounded-lg overflow-hidden bg-black">
                    <video
                      controls
                      className="w-full max-h-96"
                      src={`/api/video/videos/${video.id}/stream`}
                      ref={(videoElement) => {
                        if (videoElement && videoTimeOffset) {
                          // Seek to time offset when video loads
                          videoElement.addEventListener('loadedmetadata', () => {
                            videoElement.currentTime = parseFloat(videoTimeOffset);
                          });
                        }
                      }}
                    >
                      Your browser does not support the video tag.
                    </video>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
