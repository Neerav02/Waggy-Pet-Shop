/**
 * Waggy Pet Shop 3D Background - Light Mode Animation
 * Uses Three.js to render a beautiful, subtle 3D background with amber/golden elements.
 */

try {
    // Canvas and Scene setup
    const canvas = document.querySelector('#three-bg');
    if (canvas) {
        const scene = new THREE.Scene();
        // Light airy background color matching bootstrap's #F7F7F7
        scene.background = new THREE.Color(0xfcfcfc);
        // Add subtle fog to blend distant objects
        scene.fog = new THREE.FogExp2(0xfcfcfc, 0.0025);

        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
        
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(window.innerWidth, window.innerHeight);

        // Core Object Creation 
        const objects = [];
        
        // Let's create soft floating spheres and torus shapes in Waggy's accent color #DEAD6F
        const accentColor = new THREE.Color(0xDEAD6F);
        const altColor = new THREE.Color(0x6995B1); // primary-color

        const sphereGeo = new THREE.SphereGeometry(1, 32, 32);
        const torusGeo = new THREE.TorusGeometry(1, 0.4, 16, 50);

        // Standard material with transparency
        const materialA = new THREE.MeshPhysicalMaterial({
            color: accentColor,
            metalness: 0.1,
            roughness: 0.5,
            transparent: true,
            opacity: 0.3,
            clearcoat: 0.5,
            clearcoatRoughness: 0.2
        });

        const materialB = new THREE.MeshPhysicalMaterial({
            color: altColor,
            metalness: 0.1,
            roughness: 0.5,
            transparent: true,
            opacity: 0.2,
            clearcoat: 0.5
        });

        const numObjects = window.innerWidth > 768 ? 40 : 15;

        for (let i = 0; i < numObjects; i++) {
            const isTorus = Math.random() > 0.5;
            const mesh = new THREE.Mesh(isTorus ? torusGeo : sphereGeo, Math.random() > 0.3 ? materialA : materialB);
            
            // Random positioning across a wide space
            mesh.position.x = (Math.random() - 0.5) * 80;
            mesh.position.y = (Math.random() - 0.5) * 80;
            mesh.position.z = (Math.random() - 0.5) * 80 - 20;

            // Random rotation
            mesh.rotation.x = Math.random() * Math.PI;
            mesh.rotation.y = Math.random() * Math.PI;

            const scale = Math.random() * 2 + 0.5;
            mesh.scale.set(scale, scale, scale);

            // Store custom animation data
            mesh.userData = {
                rotSpeedX: (Math.random() - 0.5) * 0.01,
                rotSpeedY: (Math.random() - 0.5) * 0.01,
                floatSpeed: Math.random() * 0.01 + 0.005,
                floatOffset: Math.random() * Math.PI * 2
            };

            scene.add(mesh);
            objects.push(mesh);
        }

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
        scene.add(ambientLight);

        const pointLight = new THREE.PointLight(0xffffff, 1);
        pointLight.position.set(20, 20, 20);
        scene.add(pointLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5);
        directionalLight.position.set(-20, 20, -20);
        scene.add(directionalLight);

        camera.position.z = 30;

        // Interaction
        let mouseX = 0;
        let mouseY = 0;
        let targetX = 0;
        let targetY = 0;

        document.addEventListener('mousemove', (event) => {
            mouseX = (event.clientX - window.innerWidth / 2) * 0.05;
            mouseY = (event.clientY - window.innerHeight / 2) * 0.05;
        });

        // Animation Loop
        const clock = new THREE.Clock();

        function animate() {
            requestAnimationFrame(animate);

            // Smooth camera movement based on mouse
            targetX = mouseX * 0.1;
            targetY = mouseY * 0.1;
            
            camera.position.x += (targetX - camera.position.x) * 0.05;
            camera.position.y += (-targetY - camera.position.y) * 0.05;
            camera.lookAt(scene.position);

            const elapsedTime = clock.getElapsedTime();

            objects.forEach((obj) => {
                // Rotation
                obj.rotation.x += obj.userData.rotSpeedX;
                obj.rotation.y += obj.userData.rotSpeedY;
                
                // Floating motion
                obj.position.y += Math.sin(elapsedTime * obj.userData.floatSpeed + obj.userData.floatOffset) * 0.02;
            });

            renderer.render(scene, camera);
        }

        animate();

        // Responsive handling
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }
} catch (e) {
    console.error("ThreeJS background error:", e);
}
