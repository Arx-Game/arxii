import { Controller, useForm } from 'react-hook-form';
import Select from 'react-select';
import { useEffect, useState } from 'react';
import { useTenureGalleriesQuery, useUploadPlayerMedia, useAssociateMedia } from '../queries';
import MyTenureSelect from '@/components/MyTenureSelect';
import { SubmitButton } from '@/components/SubmitButton';

interface Option {
  value: number;
  label: string;
}

interface UploadFormValues {
  image_file: FileList;
  title: string;
  description: string;
  tenure: number | null;
  gallery: Option | null;
}

export function MediaUploadForm({ onUploadComplete }: { onUploadComplete?: () => void }) {
  const uploadMutation = useUploadPlayerMedia();
  const associateMutation = useAssociateMedia();

  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { isValid },
  } = useForm<UploadFormValues>({
    defaultValues: { tenure: null, gallery: null },
    mode: 'onChange',
  });

  const tenureId = watch('tenure');
  const fileList = watch('image_file');
  const { data: galleries } = useTenureGalleriesQuery(tenureId ?? undefined);

  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (fileList && fileList.length > 0) {
      const url = URL.createObjectURL(fileList[0]);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }
    setPreview(null);
  }, [fileList]);

  const onSubmit = async (data: UploadFormValues) => {
    const formData = new FormData();
    formData.append('image_file', data.image_file[0]);
    if (data.title) formData.append('title', data.title);
    if (data.description) formData.append('description', data.description);
    const result = await uploadMutation.mutateAsync(formData);
    if (data.tenure) {
      await associateMutation.mutateAsync({
        mediaId: result.id,
        tenureId: data.tenure,
        galleryId: data.gallery?.value,
      });
    }
    reset();
    onUploadComplete?.();
  };

  const galleryOptions = galleries?.map((g) => ({ value: g.id, label: g.name })) ?? [];

  return (
    <section className="space-y-2">
      <h3 className="text-lg font-semibold">Upload Media</h3>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-2">
        <input type="file" {...register('image_file', { required: true })} />
        {preview && <img src={preview} alt="Preview" className="max-h-64" />}
        <input type="text" placeholder="Title" {...register('title')} className="block w-full" />
        <textarea
          placeholder="Description"
          {...register('description')}
          className="block h-32 w-full"
        />
        <Controller
          name="tenure"
          control={control}
          render={({ field }) => (
            <MyTenureSelect value={field.value} onChange={field.onChange} label="Gallery Owner" />
          )}
        />
        {tenureId && (
          <Controller
            name="gallery"
            control={control}
            render={({ field }) => (
              <Select
                {...field}
                options={galleryOptions}
                isClearable
                placeholder="Select Gallery"
                classNames={{
                  control: () => 'bg-white text-black dark:bg-slate-800 dark:text-white',
                  menu: () => 'bg-white text-black dark:bg-slate-800 dark:text-white',
                  option: (state) =>
                    state.isFocused
                      ? 'bg-slate-100 dark:bg-slate-700 text-black dark:text-white'
                      : 'text-black dark:text-white',
                }}
              />
            )}
          />
        )}
        <SubmitButton
          className="rounded bg-blue-500 px-2 py-1 text-white"
          isLoading={uploadMutation.isPending || associateMutation.isPending}
          disabled={!isValid}
        >
          Upload
        </SubmitButton>
      </form>
    </section>
  );
}
