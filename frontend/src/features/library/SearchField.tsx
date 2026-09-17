import { Search, X } from "lucide-react";

export function SearchField({
  value,
  onChange,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={`search-box ${className}`}>
      <Search size={17} />
      <input
        aria-label="사진 검색"
        placeholder="사진과 사람 검색"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button
          className="icon-button"
          onClick={() => onChange("")}
          aria-label="검색어 지우기"
        >
          <X size={14} />
        </button>
      )}
    </label>
  );
}
