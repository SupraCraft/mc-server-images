package org.supracraft.microscope;

import java.lang.instrument.Instrumentation;
import java.util.LinkedHashMap;
import java.util.Map;

public final class Agent {
    private Agent() {}

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        Map<String,String> args=parse(agentArgs);
        String adapter=value(args,"adapter","modern-26.3-java25");
        if (!"modern-26.3-java25".equals(adapter)) {
            System.err.println("SupraCraft causal microscope: unsupported adapter "+adapter);
            Runtime.getRuntime().halt(73);
        }

        // Modern Minecraft runs game classes in a child URLClassLoader.
        // The injected call target must therefore live in bootstrap visibility.
        // Boot-Class-Path in the agent manifest supplies a bridge jar containing
        // only TraceRuntime. Fail closed if packaging/class loading regresses.
        if (TraceRuntime.class.getClassLoader()!=null) {
            System.err.println(
                "SupraCraft causal microscope: TraceRuntime is not bootstrap-visible"
            );
            Runtime.getRuntime().halt(73);
        }

        String out=value(args,"out","supracraft-causal-trace.jsonl");
        String gate=value(args,"gate","");
        TraceRuntime.start(adapter,out,gate);
        final Modern263Transformer transformer=new Modern263Transformer();
        instrumentation.addTransformer(transformer,false);
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override public void run() {
                transformer.verifyComplete();
                TraceRuntime.close();
            }
        },"supracraft-causal-microscope-shutdown"));
    }

    private static String value(Map<String,String> args,String key,String fallback) {
        String value=args.get(key);
        return value==null || value.isEmpty() ? fallback : value;
    }

    private static Map<String,String> parse(String text) {
        Map<String,String> out=new LinkedHashMap<String,String>();
        if (text==null || text.trim().isEmpty()) return out;
        for (String token:text.split(",")) {
            int p=token.indexOf('=');
            if (p<=0) continue;
            out.put(token.substring(0,p).trim(),token.substring(p+1).trim());
        }
        return out;
    }
}
