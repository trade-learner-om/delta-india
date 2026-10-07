import { CRYPTOBRIDGE_LOGO_SRC } from "../../utils/documentTitle";

export default function CryptoBridgeLogo({
  size = 40,
  iconOnly = false,
  subtitle = "",
  className = "",
}) {
  const shellPad = Math.max(4, Math.round(size * 0.1));
  const imgSize = Math.max(16, size - shellPad * 2);

  const icon = (
    <div
      className="shrink-0 rounded-lg bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 flex items-center justify-center overflow-hidden"
      style={{ width: size, height: size, padding: shellPad }}
    >
      <img
        src={CRYPTOBRIDGE_LOGO_SRC}
        alt="CryptoBridge"
        width={imgSize}
        height={imgSize}
        style={{ width: imgSize, height: imgSize }}
        className="object-contain"
      />
    </div>
  );

  if (iconOnly) {
    return <div className={className}>{icon}</div>;
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {icon}
      <div>
        <span className="font-extrabold tracking-wider text-sm block text-zinc-950 dark:text-zinc-100">
          CRYPTO<span className="text-lime-500">BRIDGE</span>
        </span>
        {subtitle ? (
          <span className="text-[10px] text-zinc-500 dark:text-zinc-400 block -mt-1 font-mono uppercase tracking-widest font-bold">
            {subtitle}
          </span>
        ) : null}
      </div>
    </div>
  );
}
