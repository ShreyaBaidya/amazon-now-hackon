"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Camera, ImagePlus, Loader2, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { DishAnalysis } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

type Stage = "idle" | "preview" | "analyzing" | "error";

const ACCEPTED = "image/jpeg,image/jpg,image/png,image/webp";
const MAX_PX = 1280; // compress to this width/height max
const JPEG_QUALITY = 0.82;

/** Compress an image File to a JPEG Blob, capped at MAX_PX on the longest side. */
async function compressImage(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const { width, height } = img;
      const scale = Math.min(1, MAX_PX / Math.max(width, height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) return resolve(file);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          if (!blob) return resolve(file);
          resolve(new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" }));
        },
        "image/jpeg",
        JPEG_QUALITY,
      );
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Image load failed")); };
    img.src = url;
  });
}

export default function DishUploadModal({ open, onClose }: Props) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const resetState = () => {
    setStage("idle");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setSelectedFile(null);
    setErrorMsg("");
    // clear input values so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const pickFile = (file: File) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setSelectedFile(file);
    setStage("preview");
    setErrorMsg("");
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) pickFile(f);
  };

  const analyze = async () => {
    if (!selectedFile) return;
    setStage("analyzing");
    setErrorMsg("");
    try {
      const compressed = await compressImage(selectedFile);

      // Convert compressed image to a data URL so the result page can display it
      const imageDataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(new Error("Failed to read image"));
        reader.readAsDataURL(compressed);
      });

      const result: DishAnalysis = await api.analyzeDish(compressed);
      // Store both the analysis result and the image for the result page
      sessionStorage.setItem("dish-analysis", JSON.stringify(result));
      sessionStorage.setItem("dish-image", imageDataUrl);
      handleClose();
      router.push("/dish-result");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setErrorMsg(msg);
      setStage("error");
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
            className="absolute inset-0 z-30 bg-black/60"
          />

          {/* Modal sheet */}
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 340, damping: 34 }}
            className="absolute bottom-0 inset-x-0 z-40 bg-white rounded-t-3xl pb-safe"
          >
            {/* Handle */}
            <div className="h-1 w-10 bg-line rounded-full mx-auto mt-3 mb-1" />

            {/* Header */}
            <div className="flex items-center justify-between px-4 pt-2 pb-3">
              <div>
                <p className="font-bold text-[16px]">Search for the recipe</p>
                <p className="text-[12px] text-ink2 mt-0.5">
                  Upload a dish photo — we&apos;ll find every ingredient
                </p>
              </div>
              <button
                onClick={handleClose}
                className="h-8 w-8 rounded-full bg-paper grid place-items-center text-ink2"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-4 pb-6">
              {/* Image preview area */}
              <div
                className="relative w-full rounded-2xl overflow-hidden bg-paper border-2 border-dashed border-line"
                style={{ minHeight: 180 }}
              >
                {previewUrl ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previewUrl}
                      alt="Selected dish"
                      className="w-full object-cover"
                      style={{ maxHeight: 240 }}
                    />
                    {/* Remove button */}
                    {stage !== "analyzing" && (
                      <button
                        onClick={resetState}
                        className="absolute top-2 right-2 h-8 w-8 rounded-full bg-black/50 grid place-items-center text-white"
                        aria-label="Remove image"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                    {/* Analyzing overlay */}
                    {stage === "analyzing" && (
                      <div className="absolute inset-0 bg-black/50 grid place-items-center">
                        <div className="text-center text-white">
                          <Loader2 size={36} className="mx-auto animate-spin" />
                          <p className="text-[13px] font-semibold mt-2">Identifying dish…</p>
                          <p className="text-[11px] text-white/70 mt-0.5">Amazon Bedrock is analysing</p>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  /* Upload placeholder */
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full h-full grid place-items-center py-10 text-center"
                  >
                    <div>
                      <div className="mx-auto h-14 w-14 rounded-2xl bg-amzn-greenlite grid place-items-center mb-3">
                        <ImagePlus size={28} className="text-amzn-green" />
                      </div>
                      <p className="text-[13px] font-semibold text-amzn-green">
                        Upload an image of a dish
                      </p>
                      <p className="text-[11px] text-ink2 mt-1">JPEG, PNG or WebP · up to 5 MB</p>
                    </div>
                  </button>
                )}
              </div>

              {/* Error message */}
              {stage === "error" && errorMsg && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-2.5 text-[12.5px] text-amzn-red font-medium text-center px-2"
                >
                  {errorMsg}
                </motion.p>
              )}

              {/* Action buttons */}
              <div className="flex gap-2.5 mt-3">
                {/* Camera capture */}
                <button
                  onClick={() => cameraInputRef.current?.click()}
                  disabled={stage === "analyzing"}
                  className="flex-1 h-11 rounded-xl bg-paper border border-line flex items-center justify-center gap-2 text-[13px] font-semibold text-ink2 disabled:opacity-40"
                >
                  <Camera size={17} />
                  Camera
                </button>

                {/* Upload from gallery */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={stage === "analyzing"}
                  className="flex-1 h-11 rounded-xl bg-paper border border-line flex items-center justify-center gap-2 text-[13px] font-semibold text-ink2 disabled:opacity-40"
                >
                  <ImagePlus size={17} />
                  Gallery
                </button>
              </div>

              {/* Analyze button — only shown when an image is selected */}
              <AnimatePresence>
                {(stage === "preview" || stage === "error") && selectedFile && (
                  <motion.button
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 8 }}
                    onClick={analyze}
                    disabled={stage === "analyzing"}
                    className="mt-3 w-full rounded-2xl bg-amzn-green text-white font-bold py-3.5
                               flex items-center justify-center gap-2 disabled:opacity-60"
                  >
                    Analyse Dish
                  </motion.button>
                )}
              </AnimatePresence>
            </div>

            {/* Hidden file inputs */}
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED}
              className="hidden"
              onChange={onFileChange}
            />
            {/* Camera capture — capture="environment" opens rear camera on mobile */}
            <input
              ref={cameraInputRef}
              type="file"
              accept={ACCEPTED}
              capture="environment"
              className="hidden"
              onChange={onFileChange}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
