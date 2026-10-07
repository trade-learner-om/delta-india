export default function ChoiceSwitch({ value, options, onChange, label }) {
  return (
    <div>
      {label ? <p className="mb-1 text-sm">{label}</p> : null}
      <div className="flex rounded-full border border-white/10 p-1">
        {options.map(([id, text]) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={`flex-1 rounded-full px-3 py-1.5 text-sm ${value === id ? "bg-[#8eafc4] text-[#16181d]" : "text-[#9a958c]"}`}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
