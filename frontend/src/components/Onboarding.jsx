import { useState } from "react";
import { Activity, MapPin, User, ArrowRight, Sparkles } from "lucide-react";

export default function Onboarding({ onComplete, loading }) {
  const [disease, setDisease] = useState("");
  const [location, setLocation] = useState("");
  const [patientName, setPatientName] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!disease.trim()) return;
    onComplete({ disease: disease.trim(), location: location.trim(), patientName: patientName.trim() });
  };

  const quickDiseases = [
    "Parkinson's Disease",
    "Lung Cancer",
    "Diabetes Type 2",
    "Alzheimer's Disease",
    "Heart Disease",
    "Multiple Sclerosis",
  ];

  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Logo / Brand */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-cura-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-cura-100" />
            </div>
            <h1 className="font-display text-3xl font-semibold text-cura-50 tracking-tight">
              Curalink
            </h1>
          </div>
          <p className="text-cura-300 text-sm max-w-xs mx-auto leading-relaxed">
            Your AI-powered medical research companion. Get research-backed
            answers from the latest publications and clinical trials.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Disease Input */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-cura-400 uppercase tracking-wider mb-2">
              <Activity className="w-3.5 h-3.5" />
              Disease or Condition *
            </label>
            <input
              type="text"
              value={disease}
              onChange={(e) => setDisease(e.target.value)}
              placeholder="e.g. Parkinson's Disease"
              required
              className="w-full px-4 py-3 bg-cura-900/60 border border-cura-800 rounded-xl text-cura-50 placeholder:text-cura-700 focus:outline-none focus:border-cura-500 focus:ring-1 focus:ring-cura-500/30 transition-all"
            />
            {/* Quick select chips */}
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {quickDiseases.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDisease(d)}
                  className={`px-2.5 py-1 text-xs rounded-lg transition-all ${
                    disease === d
                      ? "bg-cura-600 text-cura-50"
                      : "bg-cura-900/40 text-cura-500 hover:bg-cura-900/70 hover:text-cura-300 border border-cura-800/50"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          {/* Location Input */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-cura-400 uppercase tracking-wider mb-2">
              <MapPin className="w-3.5 h-3.5" />
              Location (optional)
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Toronto, Canada"
              className="w-full px-4 py-3 bg-cura-900/60 border border-cura-800 rounded-xl text-cura-50 placeholder:text-cura-700 focus:outline-none focus:border-cura-500 focus:ring-1 focus:ring-cura-500/30 transition-all"
            />
          </div>

          {/* Patient Name Input */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-cura-400 uppercase tracking-wider mb-2">
              <User className="w-3.5 h-3.5" />
              Your Name (optional)
            </label>
            <input
              type="text"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              placeholder="e.g. John Smith"
              className="w-full px-4 py-3 bg-cura-900/60 border border-cura-800 rounded-xl text-cura-50 placeholder:text-cura-700 focus:outline-none focus:border-cura-500 focus:ring-1 focus:ring-cura-500/30 transition-all"
            />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!disease.trim() || loading}
            className="w-full flex items-center justify-center gap-2.5 px-6 py-3.5 bg-cura-600 hover:bg-cura-500 disabled:bg-cura-800 disabled:text-cura-600 text-cura-50 font-medium rounded-xl transition-all duration-200 mt-3"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-cura-300/30 border-t-cura-300 rounded-full animate-spin" />
                Setting up your session...
              </>
            ) : (
              <>
                Start Research
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Disclaimer */}
        <p className="text-center text-[11px] text-cura-700 mt-6 leading-relaxed max-w-sm mx-auto">
          Curalink provides research-backed information for educational purposes
          only. It is not a substitute for professional medical advice,
          diagnosis, or treatment.
        </p>
      </div>
    </div>
  );
}
