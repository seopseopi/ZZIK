import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { post } from "../../api";
import { ErrorBox, Logo } from "../../ui";

export function Login({
  demoEnabled,
  onLogin,
}: {
  demoEnabled: boolean;
  onLogin: () => void;
}) {
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const action = useMutation({
    mutationFn: (data: { email: string; password: string; name?: string }) =>
      post(register ? "/auth/register" : "/auth/login", data),
    onSuccess: onLogin,
  });
  return (
    <main className="login-page">
      <section className="login-image">
        <img
          src={`${import.meta.env.BASE_URL}demo/photo-03.jpg`}
          alt="제주 여행 앨범 표지"
        />
        <Logo light />
      </section>
      <section className="login-form-panel">
        <div className="login-form">
          <Logo />
          <h1>{register ? "회원가입" : "로그인"}</h1>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({ email, password, ...(register ? { name } : {}) });
            }}
          >
            {register && (
              <label>
                이름
                <input
                  autoComplete="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="이름"
                />
              </label>
            )}
            <label>
              이메일
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="hello@example.com"
              />
            </label>
            <label>
              비밀번호
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={register ? 10 : 1}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={register ? "10자 이상" : "비밀번호"}
              />
            </label>
            {action.error && <ErrorBox error={action.error} />}
            <button className="button primary full" disabled={action.isPending}>
              {action.isPending
                ? "처리 중…"
                : register
                  ? "계정 만들기"
                  : "로그인"}
            </button>
          </form>
          <p className="login-switch">
            {register ? "이미 계정이 있나요?" : "계정이 없나요?"}{" "}
            <button
              onClick={() => {
                setRegister(!register);
                action.reset();
              }}
            >
              {register ? "로그인" : "회원가입"}
            </button>
          </p>
          {demoEnabled && !register && (
            <button
              className="button secondary full"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  email: "jisu@moacut.local",
                  password: "MoacutDemo123!",
                })
              }
            >
              샘플 앨범 둘러보기
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
