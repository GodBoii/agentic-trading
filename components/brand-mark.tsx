import Image from "next/image";

type BrandMarkProps = {
  className?: string;
  priority?: boolean;
};

export default function BrandMark({
  className = "h-7 w-7",
  priority = false,
}: BrandMarkProps) {
  return (
    <Image
      src="/polycognition-mark.png"
      alt=""
      aria-hidden="true"
      width={512}
      height={512}
      priority={priority}
      className={`shrink-0 object-contain ${className}`}
    />
  );
}
